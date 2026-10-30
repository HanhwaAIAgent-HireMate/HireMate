package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.job.application.JobResultPublisher;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import tools.jackson.databind.json.JsonMapper;

class InterviewQuestionResultsTests {

    private final InterviewAiService interviews = mock(InterviewAiService.class);
    private final UUID companyId = UUID.randomUUID();
    private final UUID stageId = UUID.randomUUID();
    private final UUID applicationId = UUID.randomUUID();
    private final List<InterviewQuestionDraft> questions = List.of(
            new InterviewQuestionDraft("본인이 담당한 장애 대응 과정을 말해 주세요.", "이력서의 장애 대응 경험 확인"));

    @Test
    @DisplayName("결과 발행이 끝나기 전에 질문을 카드에 저장한다")
    void savesQuestionsBeforePublishingReturns() {
        try (var context = context()) {
            context.getBean(JobResultPublisher.class).publish(result(JobStatus.DONE));

            verify(interviews).addPreparedDrafts(companyId, stageId, applicationId, questions);
        }
    }

    @Test
    @DisplayName("저장 실패를 결과 수신자에게 전파해 작업을 완료로 처리하지 않는다")
    void propagatesStorageFailure() {
        var failure = new IllegalStateException("question storage failed");
        doThrow(failure).when(interviews).addPreparedDrafts(companyId, stageId, applicationId, questions);

        try (var context = context()) {
            assertThatThrownBy(() -> context.getBean(JobResultPublisher.class).publish(result(JobStatus.DONE)))
                    .isSameAs(failure);
        }
    }

    @Test
    @DisplayName("AI 생성 실패 결과는 질문을 저장하지 않고 처리를 끝낸다")
    void doesNotSaveFailedGeneration() {
        try (var context = context()) {
            context.getBean(JobResultPublisher.class).publish(result(JobStatus.FAILED));

            verify(interviews).finishPreparing(companyId, stageId, applicationId);
        }
    }

    private AnnotationConfigApplicationContext context() {
        var context = new AnnotationConfigApplicationContext();
        context.registerBean(InterviewAiService.class, () -> interviews);
        context.register(InterviewQuestionResults.class, JobResultPublisher.class);
        context.refresh();
        return context;
    }

    @Test
    @DisplayName("배포 전 문자열 작업 결과는 근거를 추측하지 않고 받는다")
    void acceptsLegacyTextQuestions() {
        var legacy = new JobResult(UUID.randomUUID(), InterviewAgent.QUESTIONS_JOB,
                InterviewAgent.jobTarget(companyId, stageId, applicationId), JobStatus.DONE,
                JsonMapper.builder().build().valueToTree(Map.of("questions", List.of("이전 질문"))), null);
        try (var context = context()) {
            context.getBean(JobResultPublisher.class).publish(legacy);
            verify(interviews).addPreparedDrafts(companyId, stageId, applicationId,
                    List.of(new InterviewQuestionDraft("이전 질문", null)));
        }
    }

    private JobResult result(JobStatus status) {
        return new JobResult(UUID.randomUUID(), InterviewAgent.QUESTIONS_JOB,
                InterviewAgent.jobTarget(companyId, stageId, applicationId), status,
                status == JobStatus.DONE ? JsonMapper.builder().build().valueToTree(Map.of("questions", questions))
                        : null,
                status == JobStatus.FAILED ? "generation failed" : null);
    }
}
