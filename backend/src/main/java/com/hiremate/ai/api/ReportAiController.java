package com.hiremate.ai.api;

import com.hiremate.ai.application.ReportComposer;
import com.hiremate.ai.application.ReportComposer.ReportPayload;
import com.hiremate.ai.application.ReportComposer.ReportSummary;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.report.AgentReportKind;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Report Agent 리포트 (RPT-01 · RPT-02): 전형 결과 · 지원자 비교 · 채용 최종 리포트. 리포트는 채용 상태를 바꾸지 않는다. */
@RestController
public class ReportAiController {

    private final ReportComposer composer;

    public ReportAiController(ReportComposer composer) {
        this.composer = composer;
    }

    /**
     * 리포트 한 건. 같은 채용의 리포트면 다른 전형 화면에서도 연다 (예: 면접 전형 Chat에서 서류 전형 리포트).
     * 쓰는 중이면 status가 PENDING이고 화면은 몇 초마다 다시 묻는다.
     */
    @GetMapping("/api/stages/{stageId}/reports/{reportId}")
    public ReportPayload report(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID reportId) {
        return composer.view(member.companyId(), stageId, reportId);
    }

    /** 전형의 리포트 목록 (kind 기본은 전형 결과). */
    @GetMapping("/api/stages/{stageId}/reports")
    public List<ReportSummary> reports(AuthenticatedMember member, @PathVariable UUID stageId,
            @RequestParam(defaultValue = "STAGE") AgentReportKind kind) {
        return composer.list(member.companyId(), stageId, kind);
    }

    /** 현재 전형 지원자 비교 리포트를 요청한다. Chat이 아닌 화면에서 부를 때 쓴다. */
    @PostMapping("/api/stages/{stageId}/reports/compare")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Requested compare(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody CompareRequest request) {
        return new Requested(composer.request(member.companyId(), stageId, AgentReportKind.COMPARE,
                request.applicationIds(), request.focus(), request.brief(), member.memberId()));
    }

    /** 전형 결과 리포트를 연다. 저장된 것이 있으면 그 ID를, 없으면 결과를 확정한 전형만 새로 만든다. */
    @PostMapping("/api/stages/{stageId}/reports/stage")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Requested stage(AuthenticatedMember member, @PathVariable UUID stageId) {
        return new Requested(composer.stageReport(member.companyId(), stageId, member.memberId()));
    }

    /** 채용 최종 리포트 목록. 최근 것이 먼저고, 조회는 각 리포트의 stageId 주소로 한다. */
    @GetMapping("/api/recruitments/{recruitmentId}/reports")
    public List<ReportSummary> finalReports(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return composer.finalReports(member.companyId(), recruitmentId);
    }

    /** 채용 최종 리포트를 연다. 저장된 것이 있으면 그것을, 없으면 종료한 채용만 새로 만든다. */
    @PostMapping("/api/recruitments/{recruitmentId}/reports/final")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ReportSummary finalReport(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return composer.finalReport(member.companyId(), recruitmentId, member.memberId());
    }

    /**
     * @param applicationIds 비교할 지원자 2~5명. 현재 전형 지원자만 들어간다
     * @param focus 관점 (예: 협업). 없으면 빈 문자열
     */
    public record CompareRequest(@NotEmpty @Size(min = 2, max = 5) List<UUID> applicationIds, String focus,
            boolean brief) {
    }

    public record Requested(UUID reportId) {
    }
}
