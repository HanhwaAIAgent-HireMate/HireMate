package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ComposedReport;
import com.hiremate.ai.application.DistributionNote;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportBundle;
import com.hiremate.ai.application.ReportDistribution;
import com.hiremate.job.JobQueue;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Report Agent를 부른다. 리포트는 AI 워커로 맡기고(작업 본문은 POST /agents/report/compose의 요청 본문과 같다),
 * 화면이 기다리는 분포 해설은 POST /agents/report/explain으로 바로 부른다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.REMOTE)
class RemoteReportAgent implements ReportAgent {

    private final JobQueue jobs;
    private final AiServerClient client;

    RemoteReportAgent(JobQueue jobs, AiServerClient client) {
        this.jobs = jobs;
        this.client = client;
    }

    @Override
    public Optional<ComposedReport> compose(UUID reportId, ReportBundle bundle) {
        jobs.enqueue(COMPOSE_JOB, reportId.toString(), Map.of("bundle", bundle));
        return Optional.empty();
    }

    @Override
    public DistributionNote explain(ReportDistribution.ForAi distribution) {
        return client.post(AiAgent.REPORT, "explain", Map.of("distribution", distribution), DistributionNote.class);
    }
}
