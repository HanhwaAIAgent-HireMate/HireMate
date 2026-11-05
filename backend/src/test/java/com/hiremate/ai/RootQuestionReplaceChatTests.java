package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/** Root가 면접 질문 교체를 요청하면 답변 없는 AI 질문만 바꾸는지 확인한다. Root는 대신 정해 둔 계획을 낸다. */
class RootQuestionReplaceChatTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("교체 요청은 답변 없는 AI 질문만 지우고, 직접 넣은 질문과 답변을 기록한 질문은 남긴 뒤 알린다")
    void replaceKeepsManualAndAnswered() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = TestFixtures.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).stream()
                .noneMatch(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID id = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(id,
                ApplicationAnalysis.of(3, "OO카드", List.of()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.ANSWER, "답", List.of(), List.of(),
                List.of()));
        String interview = passAndFinish(hr, document, id.toString());

        when(root.plan(any(), any())).thenReturn(questions(id, false));
        done(expect(hr.post(TestFixtures.firstTabPath(hr, interview) + "/chat",
                Map.of("message", "면접 질문 만들어줘", "mentionIds", List.of(id), "checkedIds", List.of())), 200));
        expect(hr.post(interview + "/candidates/" + id + "/interview/questions", Map.of("text", "직접 넣은 질문")), 200);
        JsonNode before = json(expect(hr.get(interview + "/candidates/" + id + "/interview"), 200)).path("questions");
        List<String> unanswered = new ArrayList<>();
        String answered = null;
        String manual = null;
        for (JsonNode question : before) {
            String questionId = question.path("questionId").asString();
            if (question.path("source").asString().equals("MANUAL")) {
                manual = questionId;
            } else if (answered == null) {
                answered = questionId;
            } else {
                unanswered.add(questionId);
            }
        }
        assertThat(manual).isNotNull();
        assertThat(unanswered).isNotEmpty();
        expect(hr.put(interview + "/interview/questions/" + answered + "/answer", Map.of("answer", "기록한 답변")), 200);

        when(root.plan(any(), any())).thenReturn(questions(id, true));
        JsonNode chat = done(expect(hr.post(TestFixtures.firstTabPath(hr, interview) + "/chat",
                Map.of("message", "면접 질문 다시 만들어줘", "mentionIds", List.of(id), "checkedIds", List.of())), 200));

        JsonNode after = json(expect(hr.get(interview + "/candidates/" + id + "/interview"), 200)).path("questions");
        List<String> ids = new ArrayList<>();
        after.forEach(question -> ids.add(question.path("questionId").asString()));
        assertThat(ids).contains(manual, answered).doesNotContainAnyElementsOf(unanswered);
        assertThat(after.size()).isGreaterThan(2);
        assertThat(chat.path("message").asString()).contains("직접 넣은 질문 1개와 답변을 기록한 질문 1개는 남겼어요.");
    }

    private static ChatPlan questions(UUID id, boolean replace) {
        return new ChatPlan(ChatPlan.Intent.ANSWER, null, null, List.of(), "1명의 면접 질문 생성을 요청했어요.", List.of(),
                List.of(), List.of("Interview Agent"), List.of(id), Map.of(), Map.of(), replace);
    }

    private static String passAndFinish(TestApi hr, String stagePath, String applicationId) throws Exception {
        expect(hr.post(stagePath + "/decisions", Map.of("applicationIds", List.of(applicationId), "decision", "PASS")),
                204);
        expect(hr.post(stagePath + "/confirm", null), 200);
        expect(hr.post(stagePath + "/notices/prepare", null), 200);
        scheduleNextInterview(hr, stagePath);
        expect(hr.post(stagePath + "/notices/PASS/send", null), 200);
        return "/api/stages/" + json(expect(hr.post(stagePath + "/finish", null), 200)).path("nextStageId").asString();
    }
}
