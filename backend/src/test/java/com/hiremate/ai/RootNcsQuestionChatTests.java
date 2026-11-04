package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.CitedQuestionDraft;
import com.hiremate.ai.application.InterviewAgent;
import com.hiremate.ai.application.NcsUse;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.interview.InterviewQuestionDraft;
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

/** Root가 NCS 참고를 정한 면접 질문 요청을 backend가 면접 Agent에 넘기고, 참고하지 못하면 알리는지 확인한다. */
class RootNcsQuestionChatTests extends IntegrationTest {

    private static final String MISSED = "요청하신 NCS를 참고하지 못해, NCS 없이 질문을 만들었어요.";

    @MockitoBean
    private RootAgent root;

    @MockitoBean
    private InterviewAgent interviewAgent;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("NCS를 요청했는데 인용한 질문이 없으면 Chat 답 끝에 알린다")
    void requestedWithoutCitationIsNoticed() throws Exception {
        Stage stage = interviewStage("applicant-a@example.com");
        when(interviewAgent.citedQuestions(any(), any(), any(), any(), any(), any(), anyInt(), eq(NcsUse.REQUESTED)))
                .thenReturn(List.of(new CitedQuestionDraft("배치 재처리 기준을 설명해 주세요.", "근거", null, false)));
        when(root.plan(any(), any())).thenReturn(questions(List.of(stage.id()), NcsUse.REQUESTED));

        JsonNode chat = chat(stage, "NCS 참고해서 면접 질문 만들어줘");

        assertThat(chat.path("message").asString()).endsWith(MISSED);
        assertThat(stage.questions()).contains("배치 재처리 기준을 설명해 주세요.");
    }

    @Test
    @DisplayName("인용한 질문이 있으면 알리지 않는다")
    void citedIsSilent() throws Exception {
        Stage stage = interviewStage("applicant-b@example.com");
        when(interviewAgent.citedQuestions(any(), any(), any(), any(), any(), any(), anyInt(), eq(NcsUse.REQUESTED)))
                .thenReturn(List.of(new CitedQuestionDraft("배치 재처리 기준을 설명해 주세요.", "근거", null, true)));
        when(root.plan(any(), any())).thenReturn(questions(List.of(stage.id()), NcsUse.REQUESTED));

        JsonNode chat = chat(stage, "NCS 참고해서 면접 질문 만들어줘");

        assertThat(chat.path("message").asString()).doesNotContain(MISSED);
    }

    @Test
    @DisplayName("도움이 될 때 참고한 요청은 못 찾아도 알리지 않는다")
    void helpfulIsSilent() throws Exception {
        Stage stage = interviewStage("applicant-c@example.com");
        when(interviewAgent.citedQuestions(any(), any(), any(), any(), any(), any(), anyInt(), eq(NcsUse.HELPFUL)))
                .thenReturn(List.of(new CitedQuestionDraft("배치 재처리 기준을 설명해 주세요.", "근거", null, false)));
        when(root.plan(any(), any())).thenReturn(questions(List.of(stage.id()), NcsUse.HELPFUL));

        JsonNode chat = chat(stage, "배치 처리 쪽 직무 지식 질문 하나 만들어줘");

        assertThat(chat.path("message").asString()).doesNotContain(MISSED);
    }

    @Test
    @DisplayName("SKIP이면 지금처럼 questions만 부르고 NCS 경로를 타지 않는다")
    void skipUsesExistingCall() throws Exception {
        Stage stage = interviewStage("applicant-d@example.com");
        when(interviewAgent.questions(any(), any(), any(), any(), any(), any(), anyInt()))
                .thenReturn(List.of(new InterviewQuestionDraft("결제 API에서 맡은 부분을 설명해 주세요.", "근거")));
        when(root.plan(any(), any())).thenReturn(questions(List.of(stage.id()), NcsUse.SKIP));

        JsonNode chat = chat(stage, "면접 질문 만들어줘");

        verify(interviewAgent, times(1)).questions(any(), any(), any(), any(), any(), any(), anyInt());
        verify(interviewAgent, never()).citedQuestions(any(), any(), any(), any(), any(), any(), anyInt(), any());
        assertThat(chat.path("message").asString()).doesNotContain(MISSED);
    }

    @Test
    @DisplayName("옛 계획처럼 questionNcs가 없으면 SKIP이다")
    void missingNcsIsSkip() {
        ChatPlan plan = new ChatPlan(ChatPlan.Intent.ANSWER, null, null, List.of(), "답", List.of(), List.of(),
                List.of(), List.of(), Map.of(), Map.of(), false, null);

        assertThat(plan.questionNcs()).isEqualTo(NcsUse.SKIP);
    }

    private record Stage(TestApi hr, String path, UUID id) {

        List<String> questions() throws Exception {
            JsonNode view = json(expect(hr.get(path + "/candidates/" + id + "/interview"), 200)).path("questions");
            return view.valueStream().map(question -> question.path("text").asString()).toList();
        }
    }

    private Stage interviewStage(String email) throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = TestFixtures.form(email, false);
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
        applications.recordAnalysis(id, ApplicationAnalysis.of(3, "OO카드", List.of()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.ANSWER, "답", List.of(), List.of(),
                List.of()));
        expect(hr.post(document + "/decisions", Map.of("applicationIds", List.of(id.toString()), "decision", "PASS")),
                204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String interview = "/api/stages/"
                + json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();
        return new Stage(hr, interview, id);
    }

    private static JsonNode chat(Stage stage, String message) throws Exception {
        return done(expect(stage.hr().post(TestFixtures.firstTabPath(stage.hr(), stage.path()) + "/chat",
                Map.of("message", message, "mentionIds", List.of(stage.id()), "checkedIds", List.of())), 200));
    }

    private static ChatPlan questions(List<UUID> ids, NcsUse ncs) {
        return new ChatPlan(ChatPlan.Intent.ANSWER, null, null, List.of(), "1명의 면접 질문 생성을 요청했어요.", List.of(),
                List.of(), List.of("Interview Agent"), ids, Map.of(), Map.of(), false, null, ncs);
    }
}
