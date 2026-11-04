package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.notice.NoticeService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import com.hiremate.report.AgentReportKind;
import com.hiremate.report.AgentReportService;
import com.hiremate.report.AgentReportStatus;
import com.hiremate.report.AgentReportView;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Report Agent 리포트 요청과 조회. 결과 확정 때 전형 결과 리포트를(안내를 모두 보낸 뒤 열린다), 채용 종료 때 최종
 * 리포트를, Chat · 화면 요청 때 지원자 비교 리포트를 만든다.
 * 리포트는 채용 상태를 바꾸지 않는다. 묶음은 지원자번호로만 Agent에 넘기고, 화면에 줄 때 이름을 붙인다.
 */
@Service
public class ReportComposer {

    private final ReportBundles bundles;
    private final ReportAgent agent;
    private final AgentReportService reports;
    private final ApplicationService applications;
    private final RecruitService recruits;
    private final NoticeService notices;
    private final JsonMapper json;

    ReportComposer(ReportBundles bundles, ReportAgent agent, AgentReportService reports,
            ApplicationService applications, RecruitService recruits, NoticeService notices, JsonMapper json) {
        this.bundles = bundles;
        this.agent = agent;
        this.reports = reports;
        this.applications = applications;
        this.recruits = recruits;
        this.notices = notices;
        this.json = json;
    }

    /**
     * 리포트를 요청한다. 묶음을 만들어 저장하고 Report Agent에 맡긴다. 결과는 AI 워커가 끝내면 저장된다.
     *
     * @param targets 비교 대상 지원서 ID. 비교 리포트가 아니면 빈 목록
     * @param requestedBy 요청한 담당자. 결과 확정 때 자동으로 만들면 null
     * @return 리포트 ID. 화면은 이 ID로 상태를 다시 물어 다 쓰면 연다
     */
    public UUID request(UUID companyId, UUID stageId, AgentReportKind kind, Collection<UUID> targets, String focus,
            boolean brief, UUID requestedBy) {
        if (!documentStage(companyId, stageId)) {
            // 팀 결정(11/03): 직무역량 평가 · 면접 전형은 비교 · 전형 결과 리포트를 쓰지 않는다. 흐름은 채용 최종 리포트가 모은다
            throw new ApiException(HttpStatus.CONFLICT, "REPORT_DOCUMENT_ONLY",
                    "Comparison and stage reports are only for document stages.");
        }
        ReportBundle bundle = bundles.build(companyId, stageId, ReportBundle.Kind.valueOf(kind.name()), targets,
                focus, brief);
        return compose(companyId, kind, requestedBy, bundle);
    }

    /**
     * 채용 최종 리포트를 요청한다. 범위는 모든 전형이고, 리포트는 마지막 전형에 붙는다.
     *
     * @param requestedBy 요청한 담당자. 채용 종료 때 자동으로 만들면 null
     */
    public UUID requestFinal(UUID companyId, UUID recruitmentId, UUID requestedBy) {
        return compose(companyId, AgentReportKind.FINAL, requestedBy, bundles.buildFinal(companyId, recruitmentId));
    }

    private UUID compose(UUID companyId, AgentReportKind kind, UUID requestedBy, ReportBundle bundle) {
        UUID reportId = reports.start(companyId, bundle.recruitmentId(), bundle.stageId(), kind, requestedBy,
                bundle.focus(), bundle.brief(), json.writeValueAsString(bundle));
        agent.compose(reportId, bundle).ifPresent(composed -> reports.complete(reportId,
                json.writeValueAsString(composed.withoutBundle()),
                composed.bundle() == null ? null : json.writeValueAsString(composed.bundle())));
        return reportId;
    }

    /** 서류 전형인가. 비교 · 전형 결과 리포트는 서류 전형만 만든다. */
    public boolean documentStage(UUID companyId, UUID stageId) {
        return recruits.getByStage(companyId, stageId).stage(stageId).map(StageInfo::type)
                .filter(type -> type == StageType.DOCUMENT).isPresent();
    }

    /** 전형의 가장 최근 전형 결과 리포트. 실패한 리포트는 건너뛴다. 없으면 null이다. */
    public UUID latestStageReport(UUID companyId, UUID stageId) {
        return reports.stageReports(companyId, stageId, AgentReportKind.STAGE).stream()
                .filter(report -> report.status() != AgentReportStatus.FAILED).findFirst()
                .map(AgentReportView::id).orElse(null);
    }

    /**
     * 전형 결과 리포트를 연다. 결과를 확정하고 합격 · 불합격 안내를 모두 보낸 전형만 연다. 저장된 것이 있으면 그것을,
     * 없거나 실패했으면 새로 만든다.
     *
     * @return 리포트 ID
     */
    public UUID stageReport(UUID companyId, UUID stageId, UUID requestedBy) {
        StageInfo stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (stage.confirmedAt() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_CONFIRMED",
                    "Confirm the stage results first.");
        }
        if (!stageReportOpen(companyId, stageId)) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICES_NOT_SENT", "Send all notices first.");
        }
        UUID latest = latestStageReport(companyId, stageId);
        return latest != null ? latest
                : request(companyId, stageId, AgentReportKind.STAGE, List.of(), "", false, requestedBy);
    }

    /** 전형 결과 리포트를 볼 수 있는가. 결과를 확정한 뒤 합격 · 불합격 안내를 모두 보내야 열린다. */
    public boolean stageReportOpen(UUID companyId, UUID stageId) {
        return notices.allSent(companyId, stageId);
    }

    /**
     * 채용 최종 리포트를 연다. 저장된 것이 있으면 그것을, 없거나 실패했으면 종료한 채용만 새로 만든다.
     *
     * @return 리포트 ID와 붙은 전형 (조회 주소에 쓴다)
     */
    public ReportSummary finalReport(UUID companyId, UUID recruitmentId, UUID requestedBy) {
        var latest = finalReports(companyId, recruitmentId).stream()
                .filter(report -> !report.status().equals(AgentReportStatus.FAILED.name())).findFirst();
        if (latest.isPresent()) {
            return latest.get();
        }
        if (recruits.get(companyId, recruitmentId).status() != RecruitmentStatus.CLOSED) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_NOT_CLOSED", "Close the recruitment first.");
        }
        return summary(reports.view(companyId, requestFinal(companyId, recruitmentId, requestedBy)));
    }

    /** 채용의 최종 리포트 목록. 최근 것이 먼저다. */
    public List<ReportSummary> finalReports(UUID companyId, UUID recruitmentId) {
        return reports.recruitmentReports(companyId, recruitmentId, AgentReportKind.FINAL).stream()
                .map(ReportComposer::summary).toList();
    }

    /** 화면에 줄 리포트. 지원자번호에 이름을 붙인다 (이름은 Agent에 넘기지 않는다). 다른 채용의 리포트는 없는 것으로 본다. */
    public ReportPayload view(UUID companyId, UUID stageId, UUID reportId) {
        UUID recruitmentId = recruits.getByStage(companyId, stageId).id();
        AgentReportView report = reports.view(companyId, reportId);
        if (!report.recruitmentId().equals(recruitmentId)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "The report does not exist.");
        }
        if (report.kind() == AgentReportKind.STAGE && !stageReportOpen(companyId, report.stageId())) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICES_NOT_SENT", "Send all notices first.");
        }
        ReportBundle bundle = json.readValue(report.bundle(), ReportBundle.class);
        Map<String, String> names = applications.applicants(companyId,
                bundle.applicants().stream().map(ReportBundle.Applicant::applicationId).toList()).stream()
                .collect(Collectors.toMap(info -> ReportBundles.number(info.applicationNo()), ApplicantInfo::name,
                        (first, second) -> first));
        ComposedReport composed = report.result() == null ? null
                : json.readValue(report.result(), ComposedReport.class);
        return new ReportPayload(report.id(), report.kind(), report.status().name(), report.stageId(),
                report.createdAt(), report.finishedAt(), reports.expectedSeconds(companyId, report.kind()),
                report.error(), json.valueToTree(bundle), composed, names);
    }

    /** 전형의 리포트 목록. 최근 것이 먼저다. */
    public List<ReportSummary> list(UUID companyId, UUID stageId, AgentReportKind kind) {
        return reports.stageReports(companyId, stageId, kind).stream().map(ReportComposer::summary).toList();
    }

    private static ReportSummary summary(AgentReportView report) {
        return new ReportSummary(report.id(), report.kind(), report.status().name(), report.stageId(),
                report.focus(), report.brief(), report.createdAt());
    }

    /**
     * 화면에 줄 리포트 한 건.
     *
     * @param status PENDING이면 쓰는 중, FAILED면 다시 요청할 수 있다
     * @param bundle Agent에 넘긴 묶음 그대로 (그래프의 값)
     * @param report 다 쓰기 전이거나 실패했으면 null
     * @param names 지원자번호 → 이름
     * @param expectedSeconds 같은 종류 리포트를 보통 다 쓰는 데 걸린 시간(초). 쓰는 중 진행률을 어림하는 데 쓴다
     */
    public record ReportPayload(UUID id, AgentReportKind kind, String status, UUID stageId, Instant createdAt,
            @Schema(nullable = true) Instant finishedAt, int expectedSeconds, @Schema(nullable = true) String error,
            JsonNode bundle,
            @Schema(nullable = true) ComposedReport report, Map<String, String> names) {
    }

    /**
     * 리포트 목록의 한 건.
     *
     * @param stageId 리포트가 붙은 전형. 최종 리포트는 마지막 전형이다. 리포트 조회 주소에 쓴다
     */
    public record ReportSummary(UUID id, AgentReportKind kind, String status, UUID stageId, String focus,
            boolean brief, Instant createdAt) {
    }
}
