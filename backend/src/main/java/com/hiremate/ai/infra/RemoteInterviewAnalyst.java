package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.InterviewAnalysisInput;
import com.hiremate.ai.application.InterviewAnalyst;
import com.hiremate.job.JobQueue;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Interview Agent(답변 분석)를 AI 워커로 부른다. 워커가 확인된 점 · 확인되지 않은 점을 지원자 프로필에 저장한다.
 * 작업 본문은 ai 서버 경로 POST /agents/interview-analyst/analyze의 요청 본문과 같다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.INTERVIEW_ANALYST, mode = AiMode.REMOTE)
class RemoteInterviewAnalyst implements InterviewAnalyst {

    private final JobQueue jobs;

    RemoteInterviewAnalyst(JobQueue jobs) {
        this.jobs = jobs;
    }

    @Override
    public Optional<AnalyzeResult> analyze(InterviewAnalysisInput input) {
        jobs.enqueue(ANALYZE_JOB, InterviewAnalyst.jobTarget(input.companyId(), input.stageId(), input.applicationId()),
                Map.of("input", input));
        return Optional.empty();
    }
}
