package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportInput;
import com.hiremate.job.JobQueue;
import com.hiremate.report.ReportContent;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Report Agent를 AI 워커로 부른다. 인원과 숫자는 워커가 입력 값을 그대로 옮기고, 합격 근거와 특이사항 문장만
 * 모델이 쓴다. 작업 본문은 ai 서버 경로 POST /agents/report/write의 요청 본문과 같다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.REMOTE)
class RemoteReportAgent implements ReportAgent {

    private final JobQueue jobs;

    RemoteReportAgent(JobQueue jobs) {
        this.jobs = jobs;
    }

    @Override
    public Optional<ReportContent> write(UUID companyId, UUID recruitmentId, ReportInput input) {
        jobs.enqueue(WRITE_JOB, ReportAgent.jobTarget(companyId, recruitmentId), Map.of("input", input));
        return Optional.empty();
    }
}
