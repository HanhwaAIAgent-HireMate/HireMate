package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.SelectionMode;
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
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));

        expect(setup.hr().post(setup.path() + "/chat",
                Map.of("message", "금융 경험 찾아줘", "mentionIds", List.of(), "checkedIds", List.of())), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root).plan(sent.capture(), any());
        assertThat(sent.getValue().threadId()).isEqualTo(threadId);
        assertThat(sent.getValue().selectable()).isTrue();

        ChatPlan found = new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null, List.of(setup.applicant()),
                "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요.", List.of(), List.of(), List.of(), List.of());
        when(root.history(threadId)).thenReturn(List.of(new ChatHistoryTurn("금융 경험 찾아줘", found, 3),
                new ChatHistoryTurn("경력 알려줘", ChatPlan.answer(ChatPlan.Intent.ANSWER, "3년이에요.", List.of(),
                        List.of(), List.of()), 3, List.of(setup.applicant(), UUID.randomUUID()),
                        List.of("요청을 확인하고 있어요", "지원자 자료를 확인하고 있어요"), 4)));
        JsonNode history = json(expect(setup.hr().get(setup.path() + "/chat"), 200));
        assertThat(history.get(0).path("message").asString()).isEqualTo("금융 경험 찾아줘");
        assertThat(history.get(0).path("answer").path("intent").asString()).isEqualTo("FIND");
        assertThat(history.get(0).path("answer").path("message").asString())
                .isEqualTo("지원자 3명 중 조건에 맞는 **1명**을 선택했어요.");
        assertThat(history.get(0).path("mentions")).isEmpty();
        assertThat(history.get(0).path("steps")).isEmpty();
        assertThat(history.get(0).path("seconds").isNull()).isTrue();
        // 멘션은 지금 전형의 지원자 이름으로 돌려주고, 전형에 없는 지원자는 뺀다
        JsonNode mentioned = history.get(1);
        assertThat(mentioned.path("mentions")).hasSize(1);
        assertThat(mentioned.path("mentions").get(0).path("applicationId").asString())
                .isEqualTo(setup.applicant().toString());
        assertThat(mentioned.path("mentions").get(0).path("name").asString()).isEqualTo("지원자1");
        assertThat(mentioned.path("steps")).extracting(JsonNode::asString)
                .containsExactly("요청을 확인하고 있어요", "지원자 자료를 확인하고 있어요");
        assertThat(mentioned.path("seconds").asInt()).isEqualTo(4);

        expect(setup.hr().delete(setup.path() + "/chat"), 204);
        verify(root).forget(threadId);

        TestApi other = newHr();
        expect(other.get(setup.path() + "/chat"), 404);
    }

    @Test
    @DisplayName("Chat은 채용의 전형 구성을 순서와 진행 상태와 함께 Root에 넘긴다")
    void chatSendsStagePlan() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));

        expect(setup.hr().post(setup.path() + "/chat",
                Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of())), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root).plan(sent.capture(), any());
        List<ChatContext.Stage> stages = sent.getValue().stages();
        assertThat(stages.getFirst()).extracting(ChatContext.Stage::id, ChatContext.Stage::type,
                ChatContext.Stage::status).containsExactly(setup.stageId(), StageType.DOCUMENT, StageStatus.ACTIVE);
        List<ChatContext.Stage> later = stages.subList(1, stages.size());
        assertThat(later).isNotEmpty().allMatch(stage -> stage.status() == StageStatus.PENDING);
        assertThat(later).extracting(ChatContext.Stage::type).contains(StageType.INTERVIEW);
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

    @Test
    @DisplayName("확정한 전형은 선택 지원자를 바꿀 수 없다고 Root에 알리고, 끝난 전형은 대화방 없이 Root를 부른다")
    void closedStagesLimitChat() throws Exception {
        Setup setup = documentStage();
        TestApi hr = setup.hr();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));
        Map<String, Object> ask = Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of());
        expect(hr.post(setup.path() + "/decisions",
                Map.of("applicationIds", List.of(setup.applicant()), "decision", "PASS")), 204);
        expect(hr.post(setup.path() + "/confirm", null), 200);
        expect(hr.post(setup.path() + "/chat", ask), 200);
        expect(hr.post(setup.path() + "/notices/prepare", null), 200);
        expect(hr.post(setup.path() + "/notices/PASS/send", null), 200);
        expect(hr.post(setup.path() + "/finish", null), 200);

        expect(hr.post(setup.path() + "/chat", ask), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root, times(2)).plan(sent.capture(), any());
        assertThat(sent.getAllValues()).extracting(ChatContext::selectable).containsExactly(false, false);
        assertThat(sent.getAllValues().get(0).threadId()).isNotEmpty();
        assertThat(sent.getAllValues().get(1).threadId()).isEmpty();
    }

    private Setup documentStage() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = TestFixtures.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).stream()
                .noneMatch(applicant -> applicant.documentScore() != null) && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID applicant = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(applicant,
                ApplicationAnalysis.of(3, "OO카드", BigDecimal.valueOf(90), true, false, List.of()));
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
