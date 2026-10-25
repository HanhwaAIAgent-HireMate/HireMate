package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.PostingCriteriaAgent;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.json.JsonMapper;

class RemotePostingCriteriaAgentTests {

    private static final PostingContent CONTENT = new PostingContent("백엔드 개발자", "백엔드 개발", "정규직",
            "경력 3년 이상", "서울 중구", "", List.of("API 개발"), List.of("Java 서버 개발 경력 3년 이상"),
            List.of("금융 도메인 경험"), List.of("유연 근무"));

    @Test
    @DisplayName("ai 서버의 posting/draftCriterion으로 공고와 항목을 보내고 유형 · 판정 기준 초안을 받는다")
    void draftsCriterionThroughAiServer() {
        PostingCriteriaAgent.CriterionDraft answer = new PostingCriteriaAgent.CriterionDraft(
                ScreeningRubric.CriterionType.CONDITION, "재직 경력이 3년 이상이다.", null, "경력이 확인되지 않는다.",
                List.of());
        RecordingClient client = new RecordingClient(answer);

        PostingCriteriaAgent.CriterionDraft draft = new RemotePostingCriteriaAgent(client).draftCriterion(CONTENT,
                ScreeningRubric.Category.QUALIFICATION, "Java 서버 개발 경력 3년 이상", null);

        assertThat(draft).isEqualTo(answer);
        assertThat(client.agent).isEqualTo(AiAgent.POSTING);
        assertThat(client.method).isEqualTo("draftCriterion");
        assertThat(client.body).containsEntry("posting", CONTENT)
                .containsEntry("category", ScreeningRubric.Category.QUALIFICATION)
                .containsEntry("text", "Java 서버 개발 경력 3년 이상")
                .containsEntry("ncsUnitCode", null);
    }

    @Test
    @DisplayName("ai 서버의 posting/recommendImportant로 공고를 보내고 '중요' 추천을 받는다")
    void recommendsImportantThroughAiServer() {
        PostingCriteriaAgent.ImportantAdvice answer = new PostingCriteriaAgent.ImportantAdvice(
                List.of(new PostingCriteriaAgent.ImportantItem(0, "API 개발")), List.of());
        RecordingClient client = new RecordingClient(answer);

        PostingCriteriaAgent.ImportantAdvice advice =
                new RemotePostingCriteriaAgent(client).recommendImportant(CONTENT);

        assertThat(advice).isEqualTo(answer);
        assertThat(client.method).isEqualTo("recommendImportant");
        assertThat(client.body).containsEntry("posting", CONTENT).hasSize(1);
    }

    /** ai 서버 대신 받은 요청을 기록하고 정해 둔 응답을 돌려준다. */
    private static final class RecordingClient extends AiServerClient {

        private final Object response;
        private AiAgent agent;
        private String method;
        private Map<Object, Object> body;

        RecordingClient(Object response) {
            super(WebClient.builder(), "http://ai.test", Duration.ofSeconds(1), JsonMapper.builder().build());
            this.response = response;
        }

        @Override
        <T> T post(AiAgent agent, String method, Object body, Class<T> type) {
            this.agent = agent;
            this.method = method;
            this.body = new HashMap<>((Map<?, ?>) body);
            return type.cast(response);
        }
    }
}
