package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatService;
import com.hiremate.ai.application.RootAgent;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/**
 * 면접관 모드의 AI Chat. 면접관은 자기만 보는 탭에서 묻고, Root는 그 면접관이 배정된 지원자만 받는다.
 * 선택 지원자는 바꿀 수 없고, Chat으로 만든 면접 질문은 그 지원자에서 맡은 담당으로 들어간다.
 */
class InterviewerChatTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Test
    @DisplayName("면접관 탭은 HR 탭과 나뉘고, 면접관은 HR 탭을 열 수 없다")
    void interviewerTabsAreSeparate() throws Exception {
        Room room = room();
        String tabs = room.interview().stage() + "/tabs";

        JsonNode mine = json(expect(room.kim().get(tabs), 200));
        assertThat(mine).hasSize(1);
        JsonNode shared = json(expect(room.hr().get(tabs), 200));
        assertThat(shared.toString()).doesNotContain(mine.get(0).path("id").asString());

        String hrTab = shared.get(0).path("id").asString();
        expect(room.kim().get(tabs + "/" + hrTab + "/chat"), 404);
        expect(room.kim().patch(tabs + "/" + hrTab, Map.of("name", "남의 탭")), 404);
        expect(room.hr().get(tabs + "/" + mine.get(0).path("id").asString() + "/chat"), 404);
        // 선택 지원자 편집은 면접관에게 열지 않는다
        expect(room.kim().get(tabs + "/" + mine.get(0).path("id").asString() + "/selection"), 403);
    }

    @Test
    @DisplayName("면접관 Chat의 Root 자료는 배정된 지원자뿐이고 결정은 숨기며, 찾기 · 넣기는 안내로 답한다")
    void interviewerChatIsScopedAndCannotSelect() throws Exception {
        Room room = room();
        expect(room.hr().post(room.interview().stage() + "/decisions", Map.of("applicationIds",
                List.of(room.interview().applicationId().toString()), "decision", "PASS")), 204);
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.FIND, null, null,
                List.of(room.interview().applicationId()), "{count}명을 찾았어요.", List.of(), List.of(), List.of(),
                List.of(), Map.of(), Map.of(), false));

        JsonNode answer = done(expect(room.kim().post(room.chat(), Map.of("message", "금융 경험자 찾아줘",
                "mentionIds", List.of(), "checkedIds", List.of())), 200));

        assertThat(answer.path("message").asString()).isEqualTo(ChatService.INTERVIEWER_LOCKED);
        ArgumentCaptor<ChatContext> sent = ArgumentCaptor.forClass(ChatContext.class);
        verify(root).plan(sent.capture(), any());
        ChatContext context = sent.getValue();
        assertThat(context.interviewer()).isTrue();
        assertThat(context.selectable()).isFalse();
        assertThat(context.candidates()).hasSize(1);
        assertThat(context.candidates().getFirst().decision().name()).isEqualTo("PENDING");
    }

    @Test
    @DisplayName("면접관이 Chat으로 만든 면접 질문은 그 지원자에서 맡은 담당으로 들어간다")
    void interviewerQuestionsTakeTheirRole() throws Exception {
        Room room = room();
        UUID id = room.interview().applicationId();
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.ANSWER, null, null, List.of(),
                "1명의 면접 질문 생성을 요청했어요.", List.of(), List.of(), List.of("Interview Agent"), List.of(id),
                Map.of(), Map.of(), false));

        Set<String> before = new HashSet<>();
        json(expect(room.hr().get(room.interview().candidate() + "/interview"), 200)).path("questions")
                .forEach(question -> before.add(question.path("questionId").asString()));

        // stub Interview Agent는 협업 질문을 인사 담당으로 만든다. 실무 면접관이 요청했으니 실무로 들어가야 한다
        done(expect(room.kim().post(room.chat(), Map.of("message", "@지원자 협업 경험을 확인할 질문 만들어줘",
                "mentionIds", List.of(id), "checkedIds", List.of())), 200));

        List<String> added = new ArrayList<>();
        json(expect(room.hr().get(room.interview().candidate() + "/interview"), 200)).path("questions")
                .forEach(question -> {
                    if (!before.contains(question.path("questionId").asString())) {
                        added.add(question.path("interviewerRole").asString());
                    }
                });
        // Chat으로 새로 들어온 질문은 모두 김지민이 맡은 실무 담당이다
        assertThat(added).isNotEmpty().containsOnly("PRACTICAL");
    }

    private record Room(Interview interview, TestApi kim, String tab) {

        TestApi hr() {
            return interview.hr();
        }

        String chat() {
            return interview.stage() + "/tabs/" + tab + "/chat";
        }
    }

    /** 인사는 면접관 최인사, 실무는 면접관 김지민으로 배정하고 김지민의 탭을 연 면접. */
    private Room room() throws Exception {
        Interview interview = interviewStage();
        TestApi kim = newInterviewer(interview.hr(), "김지민");
        Map<String, Object> body = new HashMap<>();
        body.put("hrMemberId", newInterviewer(interview.hr(), "최인사").memberId().toString());
        body.put("practicalMemberId", kim.memberId().toString());
        body.put("expectedVersion", null);
        expect(interview.hr().put(interview.candidate() + "/interview/session", body), 200);
        String tab = json(expect(kim.get(interview.stage() + "/tabs"), 200)).get(0).path("id").asString();
        return new Room(interview, kim, tab);
    }
}
