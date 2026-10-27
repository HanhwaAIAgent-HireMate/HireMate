package com.hiremate.ai.application;

import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/**
 * AI 워커가 미리 만든 면접 질문을 지원자 카드에 넣는다. 업무 데이터는 backend만 쓴다 (아키텍처 규칙 3).
 * 결과 수신 트랜잭션에서 저장을 끝내야 열린 작업이 닫힌 뒤 카드에서 질문을 조회할 수 있다.
 * 저장에 실패하면 예외를 전파해 결과 스트림에 남겨 두고 다시 처리한다.
 */
@Component
class InterviewQuestionResults {

    private static final Logger log = LoggerFactory.getLogger(InterviewQuestionResults.class);

    private final InterviewAiService interviews;

    InterviewQuestionResults(InterviewAiService interviews) {
        this.interviews = interviews;
    }

    @EventListener
    void on(JobFinished event) {
        JobResult result = event.result();
        if (!InterviewAgent.QUESTIONS_JOB.equals(result.type())) {
            return;
        }
        // 작업 대상: '기업 ID:전형 ID:지원서 ID' (InterviewAgent.jobTarget)
        String[] target = result.target().split(":", 3);
        UUID companyId = UUID.fromString(target[0]);
        UUID stageId = UUID.fromString(target[1]);
        UUID applicationId = UUID.fromString(target[2]);
        if (result.status() != JobStatus.DONE) {
            log.warn("Interview questions were not prepared for {} in stage {}: {}", applicationId, stageId,
                    result.error());
            return;
        }
        List<InterviewQuestionDraft> questions = new ArrayList<>();
        for (JsonNode question : result.result().path("questions")) {
            // 배포 전 대기열에 남아 있는 문자열 결과도 근거 없이 정상 수신한다.
            questions.add(question.isString() ? new InterviewQuestionDraft(question.asString(), null)
                    : new InterviewQuestionDraft(question.path("text").asString(),
                            question.path("reason").isString() ? question.path("reason").asString() : null));
        }
        interviews.addPreparedDrafts(companyId, stageId, applicationId, questions);
    }
}
