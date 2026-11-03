package com.hiremate.ai;

import static com.hiremate.TestApi.events;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatInput;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.ChatService;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.screening.CandidateFilter;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.SelectionMode;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/** AI Chat 응답 스트림(SSE): 진행 알림, 최종 답, 오류 이벤트, 화면 연결이 끊긴 경우. Root는 정해 둔 값을 낸다. */
class ChatStreamTests extends IntegrationTest {

    private static final Map<String, Object> ASK =
            Map.of("message", "강점 요약해줘", "mentionIds", List.of(), "checkedIds", List.of());

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Autowired
    private ChatService chat;

    @Autowired
    private ScreeningService screening;

    @Test
    @DisplayName("Root의 진행 알림을 status · item 이벤트로 먼저 보내고 마지막 done에 답을 보낸다")
    void streamsProgressThenDone() throws Exception {
        Setup setup = documentStage();
        ChatItem item = new ChatItem(setup.applicant(), "강점", "정산 배치 개선", "OK");
        when(root.plan(any(), any())).thenAnswer(call -> {
            ChatProgress progress = call.getArgument(1);
            progress.status("요청을 확인하고 있어요");
            progress.item(item);
            return ChatPlan.answer(ChatPlan.Intent.ANSWER, "답", List.of(item), List.of("이력서"), List.of());
        });

        HttpResponse<String> response = expect(setup.hr().post(setup.chatPath(), ASK), 200);

        assertThat(response.headers().firstValue("Content-Type")).hasValueSatisfying(
                type -> assertThat(type).startsWith("text/event-stream"));
        List<Map.Entry<String, JsonNode>> events = events(response);
        assertThat(events).extracting(Map.Entry::getKey).containsExactly("status", "item", "done");
        assertThat(events.get(0).getValue().path("text").asString()).isEqualTo("요청을 확인하고 있어요");
        assertThat(events.get(1).getValue().path("label").asString()).isEqualTo("강점");
        assertThat(events.get(2).getValue().path("message").asString()).isEqualTo("답");
        assertThat(events.get(2).getValue().path("items").get(0).path("text").asString()).isEqualTo("정산 배치 개선");
    }

    @Test
    @DisplayName("다른 기업의 전형이면 스트림을 열기 전에 404로 답한다")
    void unknownStageIs404BeforeStream() throws Exception {
        Setup setup = documentStage();

        HttpResponse<String> response = expect(newHr().post(setup.chatPath(), ASK), 404);

        assertThat(response.headers().firstValue("Content-Type")).hasValueSatisfying(
                type -> assertThat(type).doesNotContain("event-stream"));
    }

    @Test
    @DisplayName("Root를 부르지 못하면 error 이벤트에 상태와 code를 담아 보낸다")
    void rootFailureSendsErrorEvent() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenThrow(
                new ApiException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "The AI server is not available."));

        List<Map.Entry<String, JsonNode>> events = events(expect(setup.hr().post(setup.chatPath(), ASK), 200));

        assertThat(events).extracting(Map.Entry::getKey).containsExactly("error");
        assertThat(events.getLast().getValue().path("status").asInt()).isEqualTo(502);
        assertThat(events.getLast().getValue().path("code").asString()).isEqualTo("AI_UNAVAILABLE");
    }

    @Test
    @DisplayName("Root가 답하기 전에 화면 연결이 끊기면 멈추고 선택 지원자를 바꾸지 않는다")
    void disconnectBeforeDoneLeavesSelection() throws Exception {
        Setup setup = documentStage();
        TestApi hr = setup.hr();
        ChatInput input = chat.prepare(hr.companyId(), setup.stageId(), setup.tabId(), null, "금융 경험 찾아줘",
                List.of(), List.of());
        when(root.plan(any(), any())).thenAnswer(call -> {
            call.<ChatProgress>getArgument(1).status("요청을 확인하고 있어요");
            return new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null, List.of(setup.applicant()),
                    "{count}명을 선택했어요.", List.of(), List.of(), List.of(), List.of(), Map.of());
        });
        ChatProgress gone = new ChatProgress() {
            @Override
            public void status(String text) {
                throw new UncheckedIOException(new IOException("Broken pipe"));
            }

            @Override
            public void item(ChatItem item) {
                throw new UncheckedIOException(new IOException("Broken pipe"));
            }
        };

        assertThatThrownBy(() -> chat.run(input, gone)).isInstanceOf(UncheckedIOException.class);

        assertThat(screening.candidates(hr.companyId(), setup.stageId(), setup.tabId(), null,
                CandidateFilter.NONE, 0, 10).items())
                .noneMatch(CandidateRow::selected);
    }

    private Setup documentStage() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = TestFixtures.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).isEmpty() && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID applicant = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(applicant,
                ApplicationAnalysis.of(3, "OO카드", List.of()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        UUID stageId = UUID.fromString(closed.path("stages").get(0).path("id").asString());
        return new Setup(hr, stageId, applicant, TestFixtures.firstTab(hr, stageId));
    }

    private record Setup(TestApi hr, UUID stageId, UUID applicant, UUID tabId) {

        String path() {
            return "/api/stages/" + stageId;
        }

        String chatPath() {
            return path() + "/tabs/" + tabId + "/chat";
        }
    }
}
