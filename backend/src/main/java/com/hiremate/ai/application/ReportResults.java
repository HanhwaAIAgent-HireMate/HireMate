package com.hiremate.ai.application;

import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.report.ReportContent;
import com.hiremate.report.ReportService;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** AI 워커가 쓴 최종 리포트를 저장한다. 실패하면 리포트는 만들어지지 않고 로그에 남는다. */
@Component
class ReportResults {

    static final String AGENT = "Report Agent";

    private static final Logger log = LoggerFactory.getLogger(ReportResults.class);

    private final ReportService reports;
    private final JsonMapper json;

    ReportResults(ReportService reports, JsonMapper json) {
        this.reports = reports;
        this.json = json;
    }

    @ApplicationModuleListener
    void on(JobFinished event) {
        JobResult result = event.result();
        if (!ReportAgent.WRITE_JOB.equals(result.type())) {
            return;
        }
        String[] target = result.target().split(":", 2);
        UUID companyId = UUID.fromString(target[0]);
        UUID recruitmentId = UUID.fromString(target[1]);
        if (result.status() != JobStatus.DONE) {
            log.warn("Report was not written for recruitment {}: {}", recruitmentId, result.error());
            return;
        }
        reports.save(companyId, recruitmentId, json.treeToValue(result.result(), ReportContent.class), AGENT);
    }
}
