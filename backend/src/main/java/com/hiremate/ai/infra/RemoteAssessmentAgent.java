package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import com.hiremate.job.JobQueue;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Assessment Agent를 AI 워커로 부른다. 점수 · 등급은 보내기만 하고, 워커가 강점 · 약점과 근거를 지원자 프로필에
 * 저장한다. 작업 본문은 ai 서버 경로 POST /agents/assessment/analyze의 요청 본문과 같다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.ASSESSMENT, mode = AiMode.REMOTE)
class RemoteAssessmentAgent implements AssessmentAgent {

    private final JobQueue jobs;

    RemoteAssessmentAgent(JobQueue jobs) {
        this.jobs = jobs;
    }

    @Override
    public Optional<AnalyzeResult> analyze(AssessmentInput input) {
        jobs.enqueue(ANALYZE_JOB, input.applicationId().toString(), Map.of("input", input));
        return Optional.empty();
    }
}
