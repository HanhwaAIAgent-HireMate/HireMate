package com.hiremate.ai;

import static com.hiremate.TestApi.events;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.after;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatAsker;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.AnalysisStatus;
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
import java.util.Optional;
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
    @DisplayName("Chat은 탭 대화방(기업:전형:탭)으로 Root를 부르고 기록도 그 대화방에서 읽으며, 탭마다 대화방이 따로다")
    void chatUsesTabThread() throws Exception {
        Setup setup = documentStage();
        String threadId = setup.threadId(setup.tabId());
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));
        Map<String, Object> ask = Map.of("message", "금융 경험 찾아줘", "mentionIds", List.of(), "checkedIds", List.of());

        expect(setup.hr().post(setup.chatPath(setup.tabId()), ask), 200);
        UUID other = newTab(setup);
        expect(setup.hr().post(setup.chatPath(other), ask), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root, times(2)).plan(sent.capture(), any());
        assertThat(sent.getAllValues()).extracting(ChatContext::threadId)
                .containsExactly(threadId, setup.threadId(other));
        assertThat(sent.getValue().selectable()).isTrue();

        ChatPlan found = new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null, List.of(setup.applicant()),
                "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요.", List.of(), List.of(), List.of(), List.of());
        when(root.history(threadId)).thenReturn(List.of(new ChatHistoryTurn("금융 경험 찾아줘", found, 3),
                new ChatHistoryTurn("경력 알려줘", ChatPlan.answer(ChatPlan.Intent.ANSWER, "3년이에요.", List.of(),
                        List.of(), List.of()), 3, List.of(setup.applicant(), UUID.randomUUID()),
                        List.of("요청을 확인하고 있어요", "지원자 자료를 확인하고 있어요"), 4)));
        JsonNode history = json(expect(setup.hr().get(setup.chatPath(setup.tabId())), 200));
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

        // [대화 지우기]는 없다. 대화는 탭을 지울 때만 지운다
        assertThat(setup.hr().delete(setup.chatPath(setup.tabId())).statusCode()).isGreaterThanOrEqualTo(400);
        verify(root, never()).forget(any());

        expect(newHr().get(setup.chatPath(setup.tabId())), 404);
    }

    @Test
    @DisplayName("Chat은 질문한 담당자를 Root에 넘기고, 대화 기록은 턴마다 질문한 담당자를 돌려준다")
    void chatRemembersAsker() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));

        expect(setup.hr().post(setup.chatPath(setup.tabId()),
                Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of())), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root).plan(sent.capture(), any());
        assertThat(sent.getValue().asker()).isEqualTo(new ChatAsker(setup.hr().memberId(), "최은영"));

        ChatPlan answer = ChatPlan.answer(ChatPlan.Intent.ANSWER, "3년이에요.", List.of(), List.of(), List.of());
        when(root.history(setup.threadId(setup.tabId()))).thenReturn(List.of(
                new ChatHistoryTurn("경력 알려줘", answer, 3, List.of(), List.of(), 2,
                        new ChatAsker(UUID.randomUUID(), "김담당")),
                new ChatHistoryTurn("예전 질문", answer, 3)));
        JsonNode history = json(expect(setup.hr().get(setup.chatPath(setup.tabId())), 200));
        assertThat(history.get(0).path("asker").path("name").asString()).isEqualTo("김담당");
        assertThat(history.get(1).path("asker").isNull()).isTrue();
    }

    @Test
    @DisplayName("첫 답 뒤에 탭 이름을 자동 제목으로 바꿔 title 이벤트로 알리고, 그 뒤로는 제목을 다시 짓지 않는다")
    void firstAnswerNamesTab() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.ANSWER, "2명이에요.", List.of(),
                List.of(), List.of()));
        when(root.title(any(), any())).thenReturn(Optional.of("금융 경험 찾기"));
        Map<String, Object> ask = Map.of("message", "금융 경험 찾아줘", "mentionIds", List.of(), "checkedIds", List.of());

        List<Map.Entry<String, JsonNode>> first = events(expect(setup.hr().post(setup.chatPath(setup.tabId()), ask),
                200));
        assertThat(first).extracting(Map.Entry::getKey).endsWith("done", "title");
        assertThat(first.getLast().getValue().path("tabId").asString()).isEqualTo(setup.tabId().toString());
        assertThat(first.getLast().getValue().path("name").asString()).isEqualTo("금융 경험 찾기");
        verify(root).title("금융 경험 찾아줘", "2명이에요.");
        assertThat(json(expect(setup.hr().get(setup.path() + "/tabs"), 200)).get(0).path("name").asString())
                .isEqualTo("금융 경험 찾기");

        List<Map.Entry<String, JsonNode>> second = events(expect(setup.hr().post(setup.chatPath(setup.tabId()), ask),
                200));
        assertThat(second.getLast().getKey()).isEqualTo("done");
        verify(root, times(1)).title(any(), any());
    }

    @Test
    @DisplayName("차단한 질문에는 제목을 짓지 않고, 제목을 기다리는 사이 담당자가 이름을 바꾸면 그 이름을 지킨다")
    void blockedOrRenamedTabsKeepTheirNames() throws Exception {
        Setup setup = documentStage();
        Map<String, Object> ask = Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of());
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.BLOCKED, "차단", List.of(),
                List.of(), List.of()));
        expect(setup.hr().post(setup.chatPath(setup.tabId()), ask), 200);
        verify(root, never()).title(any(), any());

        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.ANSWER, "강점은 정산이에요.", List.of(),
                List.of(), List.of()));
        when(root.title(any(), any())).thenAnswer(call -> {
            expect(setup.hr().patch(setup.path() + "/tabs/" + setup.tabId(), Map.of("name", "직접 지은 이름")), 200);
            return Optional.of("자동 제목");
        });
        List<Map.Entry<String, JsonNode>> answered = events(
                expect(setup.hr().post(setup.chatPath(setup.tabId()), ask), 200));

        assertThat(answered.getLast().getKey()).isEqualTo("done");
        assertThat(json(expect(setup.hr().get(setup.path() + "/tabs"), 200)).get(0).path("name").asString())
                .isEqualTo("직접 지은 이름");
    }

    @Test
    @DisplayName("Chat은 채용의 전형 구성을 순서와 진행 상태와 함께 Root에 넘긴다")
    void chatSendsStagePlan() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));

        expect(setup.hr().post(setup.chatPath(setup.tabId()),
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
    @DisplayName("탭을 지우면 그 탭의 대화방을 지우고, 전형을 종료해도 남은 탭의 대화방은 그대로다")
    void deletingTabForgetsItsThread() throws Exception {
        Setup setup = documentStage();
        TestApi hr = setup.hr();
        UUID other = newTab(setup);
        expect(hr.delete(setup.path() + "/tabs/" + other), 204);
        verify(root, timeout(10_000)).forget(setup.threadId(other));

        expect(hr.post(setup.path() + "/decisions",
                Map.of("applicationIds", List.of(setup.applicant()), "decision", "PASS")), 204);
        expect(hr.post(setup.path() + "/confirm", null), 200);
        expect(hr.post(setup.path() + "/notices/prepare", null), 200);
        expect(hr.post(setup.path() + "/notices/PASS/send", null), 200);

        expect(hr.post(setup.path() + "/finish", null), 200);

        verify(root, after(1_000).never()).forget(setup.threadId(setup.tabId()));
    }

    @Test
    @DisplayName("확정한 전형은 선택 지원자를 바꿀 수 없다고 Root에 알리고, 끝난 전형도 탭 대화방에 대화를 남긴다")
    void closedStagesLimitChat() throws Exception {
        Setup setup = documentStage();
        TestApi hr = setup.hr();
        when(root.plan(any(), any())).thenReturn(ChatPlan.answer(ChatPlan.Intent.CLARIFY, "답", List.of(), List.of(),
                List.of()));
        Map<String, Object> ask = Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of());
        expect(hr.post(setup.path() + "/decisions",
                Map.of("applicationIds", List.of(setup.applicant()), "decision", "PASS")), 204);
        expect(hr.post(setup.path() + "/confirm", null), 200);
        expect(hr.post(setup.chatPath(setup.tabId()), ask), 200);
        expect(hr.post(setup.path() + "/notices/prepare", null), 200);
        expect(hr.post(setup.path() + "/notices/PASS/send", null), 200);
        expect(hr.post(setup.path() + "/finish", null), 200);

        expect(hr.post(setup.chatPath(setup.tabId()), ask), 200);

        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root, times(2)).plan(sent.capture(), any());
        assertThat(sent.getAllValues()).extracting(ChatContext::selectable).containsExactly(false, false);
        assertThat(sent.getAllValues()).extracting(ChatContext::threadId)
                .containsOnly(setup.threadId(setup.tabId()));
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
                .noneMatch(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID applicant = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(applicant,
                ApplicationAnalysis.of(3, "OO카드", List.of()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        UUID stageId = UUID.fromString(closed.path("stages").get(0).path("id").asString());
        return new Setup(hr, stageId, applicant, TestFixtures.firstTab(hr, stageId));
    }

    private static UUID newTab(Setup setup) throws Exception {
        return UUID.fromString(json(expect(setup.hr().post(setup.path() + "/tabs", null), 201)).path("id").asString());
    }

    private record Setup(TestApi hr, UUID stageId, UUID applicant, UUID tabId) {

        String path() {
            return "/api/stages/" + stageId;
        }

        String chatPath(UUID tab) {
            return path() + "/tabs/" + tab + "/chat";
        }

        String threadId(UUID tab) {
            return hr.companyId() + ":" + stageId + ":" + tab;
        }
    }
}
