package com.hiremate.ai.application;

import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.report.AgentReportService;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** AI 워커가 쓴 리포트 설계서를 저장한다. 실패하면 실패로 두어 담당자가 다시 요청할 수 있게 한다. */
@Component
class ReportResults {

    static final String AGENT = "Report Agent";

    private static final Logger log = LoggerFactory.getLogger(ReportResults.class);

    private final AgentReportService agentReports;
    private final JsonMapper json;

    ReportResults(AgentReportService agentReports, JsonMapper json) {
        this.agentReports = agentReports;
        this.json = json;
    }

    @ApplicationModuleListener
    void on(JobFinished event) {
        JobResult result = event.result();
        if (ReportAgent.COMPOSE_JOB.equals(result.type())) {
            composed(result);
        }
    }

    /** 부품 설계서를 리포트에 저장한다. 실패하면 실패로 두어 담당자가 다시 요청할 수 있게 한다. */
    private void composed(JobResult result) {
        UUID reportId = UUID.fromString(result.target());
        if (result.status() != JobStatus.DONE) {
            log.warn("Report {} was not composed: {}", reportId, result.error());
            agentReports.fail(reportId, result.error());
            return;
        }
        ComposedReport composed = json.treeToValue(result.result(), ComposedReport.class);
        agentReports.complete(reportId, json.writeValueAsString(composed.withoutBundle()),
                composed.bundle() == null ? null : json.writeValueAsString(composed.bundle()));
    }
}
