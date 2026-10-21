package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ApplicationAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Application Agent를 AI 워커로 부른다. {@code HIREMATE_AI_AGENTS_APPLICATION=remote}로 켠다.
 * 지원서 · 공고 · 평가 기준을 분석 작업으로 대기열에 넣고 바로 돌아온다. 작업 본문은 ai 서버 경로
 * POST /agents/application/analyze의 요청 본문과 같다. 모델이 느려도 접수와 backend 스레드가 기다리지 않는다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.REMOTE)
class RemoteApplicationAgent implements ApplicationAgent {

    private final JobQueue jobs;

    RemoteApplicationAgent(JobQueue jobs) {
        this.jobs = jobs;
    }

    @Override
    public Optional<ApplicationAnalysis> analyze(ApplicantDetail applicant, PostingContent posting,
            ScreeningRubric rubric) {
        jobs.enqueue(ANALYZE_JOB, applicant.info().applicationId().toString(),
                Map.of("applicant", applicant, "posting", posting, "rubric", rubric));
        return Optional.empty();
    }
}
