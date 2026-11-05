package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.math.BigDecimal;
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

/** Root Agent가 정리한 면접 확인할 점이 Interview Agent 호출로 이어지는지 확인한다. Root는 대신 정해 둔 계획을 낸다. */
class RootFocusChatTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("면접 전형 Chat은 면접 기록을 Root에 넘기고, Root가 준 확인할 점으로 질문을 만들며 생성 이유를 답에 남긴다")
    void rootFocusReachesInterviewAgent() throws Exception {
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
        expect(hr.put(interview + "/candidates/" + id + "/memo",
                Map.of("memo", "협업 사례의 본인 역할은 추가 확인이 필요함")), 204);

        ChatItem reason = new ChatItem(id, "확인할 점", "자기소개서의 협업 사례를 실제 역할로 확인", "OK");
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.ANSWER, null, null, List.of(),
                "1명의 맞춤 질문을 만들어 카드에 넣었어요.", List.of(reason), List.of("자기소개서"),
                List.of("Interview Agent"), List.of(id), Map.of(id, "협업 위주로 확인")));

        JsonNode chat = done(expect(hr.post(TestFixtures.firstTabPath(hr, interview) + "/chat",
                Map.of("message", "면접 질문 만들어줘", "mentionIds", List.of(id), "checkedIds", List.of())), 200));

        assertThat(chat.path("items").size()).isEqualTo(1);
        assertThat(chat.path("items").get(0).path("text").asString()).isEqualTo("자기소개서의 협업 사례를 실제 역할로 확인");
        JsonNode card = json(expect(hr.get(interview + "/candidates/" + id + "/interview"), 200));
        assertThat(card.path("questions").toString()).contains("동료와 의견이 달랐을 때");
        JsonNode manual = json(expect(hr.post(interview + "/candidates/" + id + "/interview/questions",
                Map.of("text", "직접 추가한 인사 질문", "interviewerRole", "HR")), 200));
        assertThat(manual.path("questions").toString()).contains("직접 추가한 인사 질문");
        assertThat(manual.path("questions").get(manual.path("questions").size() - 1)
                .path("interviewerRole").asString()).isEqualTo("HR");
        String introRolePath = interview + "/interview/questions/"
                + card.path("questions").get(0).path("questionId").asString() + "/role";
        expect(hr.put(introRolePath, Map.of("interviewerRole", "PRACTICAL")), 409);
        String questionId = card.path("questions").get(1).path("questionId").asString();
        String rolePath = interview + "/interview/questions/" + questionId + "/role";
        expect(hr.put(rolePath, Map.of("interviewerRole", "PRACTICAL")), 200);
        JsonNode assigned = json(expect(hr.get(interview + "/candidates/" + id + "/interview"), 200));
        assertThat(assigned.path("questions").get(1).path("interviewerRole").asString()).isEqualTo("PRACTICAL");
        expect(hr.put(rolePath, Map.of("interviewerRole", "UNKNOWN")), 400);
        expect(newHr().put(rolePath, Map.of("interviewerRole", "HR")), 404);
        expect(hr.put(rolePath, java.util.Collections.singletonMap("interviewerRole", null)), 200);
        JsonNode cleared = json(expect(hr.get(interview + "/candidates/" + id + "/interview"), 200));
        assertThat(cleared.path("questions").get(1).path("interviewerRole").isNull()).isTrue();
        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root, atLeastOnce()).plan(sent.capture(), any());
        assertThat(sent.getValue().interviews()).containsKey(id);
        assertThat(sent.getValue().interviewerMemos().get(id)).hasSize(1);
        assertThat(sent.getValue().interviewerMemos().get(id).getFirst().text())
                .isEqualTo("협업 사례의 본인 역할은 추가 확인이 필요함");
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
