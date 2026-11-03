package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.after;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.InterviewAnalyst;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/**
 * 💾 답변 자동 저장과 🎤 꼬리질문. 자동 저장은 분석을 부르지 않고, 칸을 떠날 때(analyze=true)만 분석한다.
 * 꼬리질문은 stub Interview Agent로 제안받고(답이 짧으면 2개, 길면 확인할 점 없음) 2단계까지 원래 질문 아래에 넣는다.
 */
class InterviewFollowUpTests extends IntegrationTest {

    private static final String SHORT = "병렬로 바꿨습니다.";
    private static final String LONG = "가맹점 단위로 작업을 나눠 병렬 처리했고, 처리 뒤 건수와 금액 합계를 원장과 대조해 검증했습니다.";

    @MockitoBean
    private InterviewAnalyst analyst;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("자동 저장은 분석하지 않고, 답변 칸을 떠날 때 한 번만 분석한다")
    void autosaveDoesNotAnalyze() throws Exception {
        Card card = activeInterview();
        String answer = card.stage() + "/interview/questions/" + card.questionId() + "/answer";

        JsonNode saved = json(expect(card.hr().put(answer, Map.of("answer", SHORT, "analyze", false)), 200));
        expect(card.hr().put(answer, Map.of("answer", SHORT + " 추가", "analyze", false)), 200);

        assertThat(saved.path("questions").toString()).contains(SHORT);
        // 분석은 저장이 끝난 뒤 따로(비동기로) 돈다. 앞 테스트의 분석이 늦게 도착할 수 있어 이 지원자 것만 센다
        verify(analyst, after(1_000).never())
                .analyze(argThat(input -> card.applicationId().equals(input.applicationId())));

        // 칸을 떠남: 답은 그대로지만 자동 저장만 된 답이라 분석한다
        expect(card.hr().put(answer, Map.of("answer", SHORT + " 추가", "analyze", true)), 200);
        verify(analyst, timeout(10_000)).analyze(argThat(input -> card.applicationId().equals(input.applicationId())));
        // 같은 답으로 다시 떠나면 분석하지 않는다
        expect(card.hr().put(answer, Map.of("answer", SHORT + " 추가", "analyze", true)), 200);
        verify(analyst, after(1_000).times(1))
                .analyze(argThat(input -> card.applicationId().equals(input.applicationId())));
    }

    @Test
    @DisplayName("꼬리질문: 답이 충분하면 확인할 점이 없고, 짧으면 확인 포인트가 붙은 제안 2개를 준다")
    void suggestsFollowUps() throws Exception {
        Card card = activeInterview();
        String question = card.stage() + "/interview/questions/" + card.questionId();

        // 답을 적기 전에는 모델을 부르지 않고 막는다
        expect(card.hr().post(question + "/follow-ups/suggestions", Map.of("avoid", List.of())), 409);

        expect(card.hr().put(question + "/answer", Map.of("answer", LONG, "analyze", false)), 200);
        JsonNode none = json(expect(card.hr().post(question + "/follow-ups/suggestions",
                Map.of("avoid", List.of())), 200));
        assertThat(none.path("needed").asBoolean()).isFalse();
        assertThat(none.path("suggestions")).isEmpty();

        expect(card.hr().put(question + "/answer", Map.of("answer", SHORT, "analyze", false)), 200);
        JsonNode found = json(expect(card.hr().post(question + "/follow-ups/suggestions",
                Map.of("avoid", List.of())), 200));
        assertThat(found.path("needed").asBoolean()).isTrue();
        assertThat(found.path("suggestions")).hasSize(2);
        for (JsonNode suggestion : found.path("suggestions")) {
            assertThat(suggestion.path("check").asString()).isNotBlank();
        }

        // 다시 제안: 앞서 본 제안은 다시 나오지 않는다
        String first = found.path("suggestions").get(0).path("text").asString();
        JsonNode again = json(expect(card.hr().post(question + "/follow-ups/suggestions",
                Map.of("avoid", List.of(first))), 200));
        assertThat(again.path("suggestions").toString()).doesNotContain(first);

        // 다른 기업은 볼 수 없다
        expect(newHr().post(question + "/follow-ups/suggestions", Map.of("avoid", List.of())), 404);
        // 자동 저장과 꼬리질문 제안은 답변 분석을 부르지 않는다 (이 지원자 기준)
        verify(analyst, never()).analyze(argThat(input -> card.applicationId().equals(input.applicationId())));
    }

    @Test
    @DisplayName("고른 꼬리질문은 원래 질문 바로 뒤에 담당을 이어 저장하고, 질문마다 하나씩 2단계까지만 받는다")
    void addsFollowUpsUpToTwoLevels() throws Exception {
        Card card = activeInterview();
        TestApi hr = card.hr();
        String root = card.questionId();
        expect(hr.put(card.stage() + "/interview/questions/" + root + "/role", Map.of("interviewerRole", "HR")), 200);
        expect(hr.put(card.stage() + "/interview/questions/" + root + "/answer", Map.of("answer", SHORT)), 200);

        JsonNode view = json(expect(hr.post(card.stage() + "/interview/questions/" + root + "/follow-ups",
                Map.of("text", "작업 단위는 어떻게 나눴나요?", "source", "AI", "check", "판단 기준이 없습니다.")), 200));
        JsonNode first = next(view, root);
        assertThat(first.path("text").asString()).isEqualTo("작업 단위는 어떻게 나눴나요?");
        assertThat(first.path("parentQuestionId").asString()).isEqualTo(root);
        assertThat(first.path("interviewerRole").asString()).isEqualTo("HR");
        assertThat(first.path("source").asString()).isEqualTo("AI");
        assertThat(first.path("reason").asString())
                .contains("질문 유형: 꼬리질문").contains("확인할 내용: 판단 기준이 없습니다.");

        // 질문마다 꼬리질문은 하나
        expect(hr.post(card.stage() + "/interview/questions/" + root + "/follow-ups",
                Map.of("text", "다른 꼬리질문", "source", "MANUAL")), 409);
        // 답을 적기 전에는 꼬리질문을 받지 않는다
        String firstId = first.path("questionId").asString();
        expect(hr.post(card.stage() + "/interview/questions/" + firstId + "/follow-ups",
                Map.of("text", "가맹점이 몰리면요?", "source", "MANUAL")), 409);

        expect(hr.put(card.stage() + "/interview/questions/" + firstId + "/answer",
                Map.of("answer", "가맹점별로요.")), 200);
        view = json(expect(hr.post(card.stage() + "/interview/questions/" + firstId + "/follow-ups",
                Map.of("text", "가맹점이 몰리면요?", "source", "MANUAL")), 200));
        JsonNode second = next(view, firstId);
        assertThat(second.path("parentQuestionId").asString()).isEqualTo(firstId);
        assertThat(second.path("source").asString()).isEqualTo("MANUAL");

        // 2단계 질문에는 꼬리질문을 받지 않는다 (남은 점은 다음 면접의 미확인 질문으로 넘긴다)
        String secondId = second.path("questionId").asString();
        expect(hr.put(card.stage() + "/interview/questions/" + secondId + "/answer", Map.of("answer", "나눴어요")),
                200);
        expect(hr.post(card.stage() + "/interview/questions/" + secondId + "/follow-ups/suggestions",
                Map.of("avoid", List.of())), 409);
        expect(hr.post(card.stage() + "/interview/questions/" + secondId + "/follow-ups",
                Map.of("text", "3단계", "source", "MANUAL")), 409);

        // 원래 질문을 지우면 딸린 꼬리질문도 함께 지운다
        view = json(expect(hr.delete(card.stage() + "/interview/questions/" + root), 200));
        assertThat(view.path("questions").toString()).doesNotContain(root).doesNotContain(firstId)
                .doesNotContain(secondId);
    }

    /** 목록에서 id 질문 바로 뒤의 질문 (꼬리질문은 원래 질문 바로 뒤에 온다). */
    private static JsonNode next(JsonNode view, String questionId) {
        JsonNode questions = view.path("questions");
        for (int i = 0; i < questions.size() - 1; i++) {
            if (questions.get(i).path("questionId").asString().equals(questionId)) {
                return questions.get(i + 1);
            }
        }
        throw new AssertionError("No question after " + questionId);
    }

    private record Card(TestApi hr, String stage, String questionId, UUID applicationId) {
    }

    /** 서류 합격자 한 명이 있는 진행 중 1차 면접과, 그 카드에 직접 넣은 질문 하나. */
    private Card activeInterview() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        expect(anonymous().multipart(posting.applyPath(), TestFixtures.form("follow@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = awaitAnalyzed(hr.companyId(), recruitmentId);
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", List.of(applicationId.toString()), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        scheduleNextInterview(hr, document);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String stageId = json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();
        String stage = "/api/stages/" + stageId;
        String text = "정산 배치 개선에서 직접 맡은 일은?";
        JsonNode card = json(expect(hr.post(stage + "/candidates/" + applicationId + "/interview/questions",
                Map.of("text", text)), 200));
        for (JsonNode question : card.path("questions")) {
            if (question.path("text").asString().equals(text)) {
                return new Card(hr, stage, question.path("questionId").asString(), applicationId);
            }
        }
        throw new AssertionError("Manual question was not added.");
    }

    private UUID awaitAnalyzed(UUID companyId, UUID recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            var analyzed = applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
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
