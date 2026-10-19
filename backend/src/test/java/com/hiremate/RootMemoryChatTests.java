package com.hiremate;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.screening.SelectionMode;
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

/** AI Chat 대화방: 담당자별 · 전형별 id, 기록 조회와 지우기, 전형 종료 시 지우기. Root는 정해 둔 값을 낸다. */
class RootMemoryChatTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("Chat은 담당자별 · 전형별 대화방으로 Root를 부르고, 기록 조회와 지우기도 그 대화방으로 한다")
    void chatUsesMemberStageThread() throws Exception {
        Setup setup = documentStage();
        String threadId = setup.hr().companyId() + ":" + setup.stageId() + ":" + setup.hr().memberId();
        when(root.plan(any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));

        expect(setup.hr().post(setup.path() + "/chat",
                Map.of("message", "금융 경험 찾아줘", "mentionIds", List.of(), "checkedIds", List.of())), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root).plan(sent.capture());
        assertThat(sent.getValue().threadId()).isEqualTo(threadId);

        ChatPlan found = new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null, List.of(setup.applicant()),
                "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요.", List.of(), List.of(), List.of(), List.of());
        when(root.history(threadId)).thenReturn(List.of(new ChatHistoryTurn("금융 경험 찾아줘", found, 3)));
        JsonNode history = json(expect(setup.hr().get(setup.path() + "/chat"), 200));
        assertThat(history.get(0).path("message").asString()).isEqualTo("금융 경험 찾아줘");
        assertThat(history.get(0).path("answer").path("intent").asString()).isEqualTo("FIND");
        assertThat(history.get(0).path("answer").path("message").asString())
                .isEqualTo("지원자 3명 중 조건에 맞는 **1명**을 선택했어요.");

        expect(setup.hr().delete(setup.path() + "/chat"), 204);
        verify(root).forget(threadId);

        TestApi other = newHr();
        expect(other.get(setup.path() + "/chat"), 404);
    }

    @Test
    @DisplayName("전형을 종료하면 그 전형의 대화방을 지운다")
    void finishingStageForgetsThreads() throws Exception {
        Setup setup = documentStage();
        TestApi hr = setup.hr();
        expect(hr.post(setup.path() + "/decisions",
                Map.of("applicationIds", List.of(setup.applicant()), "decision", "PASS")), 204);
        expect(hr.post(setup.path() + "/confirm", null), 200);
        expect(hr.post(setup.path() + "/notices/prepare", null), 200);
        expect(hr.post(setup.path() + "/notices/PASS/send", null), 200);

        expect(hr.post(setup.path() + "/finish", null), 200);

        verify(root, timeout(10_000)).forgetStage(setup.stageId());
    }

    private Setup documentStage() throws Exception {
        TestApi hr = newHr();
        ApplyTests.Posting posting = ApplyTests.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = ApplyTests.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).stream()
                .noneMatch(applicant -> applicant.documentScore() != null) && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID applicant = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(applicant, new ApplicationAnalysis(3, "OO카드", 90, true));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        UUID stageId = UUID.fromString(closed.path("stages").get(0).path("id").asString());
        return new Setup(hr, stageId, applicant);
    }

    private record Setup(TestApi hr, UUID stageId, UUID applicant) {

        String path() {
            return "/api/stages/" + stageId;
        }
    }
}
