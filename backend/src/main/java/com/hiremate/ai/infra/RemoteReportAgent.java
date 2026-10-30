package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ComposedReport;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportBundle;
import com.hiremate.job.JobQueue;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Report Agent를 AI 워커로 부른다. 작업 본문은 ai 서버 경로 POST /agents/report/compose의 요청 본문과 같다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.REMOTE)
class RemoteReportAgent implements ReportAgent {

    private final JobQueue jobs;

    RemoteReportAgent(JobQueue jobs) {
        this.jobs = jobs;
    }

    @Override
    public Optional<ComposedReport> compose(UUID reportId, ReportBundle bundle) {
        jobs.enqueue(COMPOSE_JOB, reportId.toString(), Map.of("bundle", bundle));
        return Optional.empty();
    }
}
