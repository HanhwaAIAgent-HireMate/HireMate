package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.after;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.InterviewAnalysisInput;
import com.hiremate.ai.application.InterviewAnalyst;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/** 면접 답변을 기록하면 Interview Agent(답변 분석)가 그 전형의 기록으로 불리는지 확인한다. Agent는 대신 기록만 하는 가짜다. */
class InterviewAnalysisTests extends IntegrationTest {

    @MockitoBean
    private InterviewAnalyst analyst;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("답변을 기록하면 이번 면접의 질문과 답변을 Interview Agent에 넘기고, 같은 답변을 다시 저장하면 넘기지 않는다")
    void recordedAnswerReachesInterviewAgent() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        expect(anonymous().multipart(posting.applyPath(), TestFixtures.form("interview@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = awaitAnalyzed(hr.companyId(), recruitmentId);
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", List.of(applicationId.toString()), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String stageId = json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();
        String stage = "/api/stages/" + stageId;
        JsonNode card = json(expect(hr.post(stage + "/candidates/" + applicationId + "/interview/questions",
                Map.of("text", "가장 어려웠던 장애 대응은?")), 200));
        String answer = stage + "/interview/questions/" + card.path("questions").get(0).path("questionId").asString()
                + "/answer";

        expect(hr.put(answer, Map.of("answer", "정산 배치가 멈췄을 때 재처리 스크립트로 당일 복구했습니다.")), 200);

        ArgumentCaptor<InterviewAnalysisInput> sent = ArgumentCaptor.forClass(InterviewAnalysisInput.class);
        verify(analyst, timeout(10_000)).analyze(sent.capture());
        InterviewAnalysisInput input = sent.getValue();
        assertThat(input.companyId()).isEqualTo(hr.companyId());
        assertThat(input.recruitmentId()).isEqualTo(recruitmentId);
        assertThat(input.stageId()).isEqualTo(UUID.fromString(stageId));
        assertThat(input.applicationId()).isEqualTo(applicationId);
        assertThat(input.stageName()).isEqualTo("1차 면접");
        assertThat(input.questions()).containsExactly(new InterviewAnalysisInput.AnsweredQuestion(
                "가장 어려웠던 장애 대응은?", "정산 배치가 멈췄을 때 재처리 스크립트로 당일 복구했습니다."));
        assertThat(input.previous()).isEmpty();

        expect(hr.put(answer, Map.of("answer", "정산 배치가 멈췄을 때 재처리 스크립트로 당일 복구했습니다.")), 200);
        verify(analyst, after(1_000)).analyze(any());
    }

    private UUID awaitAnalyzed(UUID companyId, UUID recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            var analyzed = applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.documentScore() != null)
                    .map(ApplicantInfo::applicationId)
                    .findFirst();
            if (analyzed.isPresent()) {
                return analyzed.get();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }
}
