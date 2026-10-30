package com.hiremate.report;

import com.hiremate.global.ApiException;
import com.hiremate.report.domain.AgentReport;
import com.hiremate.report.domain.AgentReportRepository;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Report Agent 리포트 저장과 조회. 리포트는 채용 상태를 바꾸지 않는다. 비교 리포트는 채용이 끝날 때까지 남는다.
 */
@Service
public class AgentReportService {

    /** 완료한 리포트가 아직 없을 때 어림하는 작성 시간(초). */
    private static final int DEFAULT_SECONDS = 45;

    private final AgentReportRepository reports;

    public AgentReportService(AgentReportRepository reports) {
        this.reports = reports;
    }

    /** 쓰는 중(PENDING) 리포트를 만든다. bundle은 Agent에 넘길 묶음 JSON이다. */
    @Transactional
    public UUID start(UUID companyId, UUID recruitmentId, UUID stageId, AgentReportKind kind, UUID requestedBy,
            String focus, boolean brief, String bundle) {
        return reports.save(new AgentReport(companyId, recruitmentId, stageId, kind, requestedBy,
                focus == null ? "" : focus, brief, bundle)).getId();
    }

    /**
     * 다 쓴 리포트를 저장한다.
     *
     * @param bundle Agent가 실제로 읽은 묶음 (분석 판정 · 근거를 붙인 것). null이면 처음 묶음을 그대로 둔다
     */
    @Transactional
    public void complete(UUID reportId, String result, String bundle) {
        reports.findById(reportId).ifPresent(report -> report.complete(result, bundle));
    }

    @Transactional
    public void fail(UUID reportId, String error) {
        reports.findById(reportId).ifPresent(report -> report.fail(error));
    }

    /** 다른 기업의 리포트는 없는 것으로 본다 (404 REPORT_NOT_FOUND). */
    @Transactional(readOnly = true)
    public AgentReportView view(UUID companyId, UUID reportId) {
        return reports.findByIdAndCompanyId(reportId, companyId).map(AgentReportService::toView).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "REPORT_NOT_FOUND", "The report does not exist."));
    }

    /** 전형의 리포트. 최근 것이 먼저다. */
    @Transactional(readOnly = true)
    public List<AgentReportView> stageReports(UUID companyId, UUID stageId, AgentReportKind kind) {
        return reports.findByCompanyIdAndStageIdAndKindOrderByCreatedAtDesc(companyId, stageId, kind).stream()
                .map(AgentReportService::toView).toList();
    }

    /** 채용의 리포트. 최근 것이 먼저다. */
    @Transactional(readOnly = true)
    public List<AgentReportView> recruitmentReports(UUID companyId, UUID recruitmentId, AgentReportKind kind) {
        return reports.findByCompanyIdAndRecruitmentIdAndKindOrderByCreatedAtDesc(companyId, recruitmentId, kind)
                .stream().map(AgentReportService::toView).toList();
    }

    /**
     * 같은 종류 리포트를 다 쓰는 데 보통 걸린 시간(초). 이 기업의 최근 완료 리포트 10건 평균이고, 없으면 기본값이다.
     * 화면은 쓰는 중 진행률을 이 시간에 견줘 어림한다.
     */
    @Transactional(readOnly = true)
    public int expectedSeconds(UUID companyId, AgentReportKind kind) {
        return (int) Math.round(reports.findTop10ByCompanyIdAndKindAndStatusOrderByCreatedAtDesc(companyId, kind,
                AgentReportStatus.DONE).stream()
                .filter(report -> report.getFinishedAt() != null)
                .mapToLong(report -> Duration.between(report.getCreatedAt(), report.getFinishedAt()).toSeconds())
                .average().orElse(DEFAULT_SECONDS));
    }

    private static AgentReportView toView(AgentReport report) {
        return new AgentReportView(report.getId(), report.getRecruitmentId(), report.getStageId(), report.getKind(),
                report.getStatus(), report.getFocus(), report.isBrief(), report.getBundle(), report.getResult(),
                report.getError(), report.getCreatedAt(), report.getFinishedAt());
    }
}
