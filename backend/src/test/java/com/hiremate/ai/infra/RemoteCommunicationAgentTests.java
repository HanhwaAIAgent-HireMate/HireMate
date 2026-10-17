package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.CommunicationAgent;
import com.hiremate.company.NoticeTemplateType;
import com.hiremate.notice.NoticeDraftContext;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

class RemoteCommunicationAgentTests {

    private static final NoticeDraftContext NOTICE = new NoticeDraftContext(UUID.randomUUID(),
            NoticeTemplateType.NEXT_STAGE, "예시 기업", "백엔드 개발자 채용", "서류 전형", "1차 면접",
            "확정 결과 · 다음 전형 정보", "");

    @Test
    @DisplayName("ai 서버의 communication/write로 안내 정보와 수정 요청을 보내고 초안을 받는다")
    void writesThroughAiServer() {
        RecordingClient client = new RecordingClient(new CommunicationAgent.Draft("초안을 만들었어요.", "본문"));

        CommunicationAgent.Draft draft = new RemoteCommunicationAgent(client).write(NOTICE, "더 따뜻하게");

        assertThat(draft).isEqualTo(new CommunicationAgent.Draft("초안을 만들었어요.", "본문"));
        assertThat(client.agent).isEqualTo(AiAgent.COMMUNICATION);
        assertThat(client.method).isEqualTo("write");
        assertThat(client.body).containsEntry("notice", NOTICE).containsEntry("request", "더 따뜻하게");
    }

    @Test
    @DisplayName("처음 초안을 쓸 때는 request를 null로 보낸다")
    void sendsNullRequestForFirstDraft() {
        RecordingClient client = new RecordingClient(new CommunicationAgent.Draft("초안을 만들었어요.", "본문"));

        new RemoteCommunicationAgent(client).write(NOTICE, null);

        assertThat(client.body).containsEntry("notice", NOTICE).containsEntry("request", null);
    }

    /** ai 서버 대신 받은 요청을 기록하고 정해 둔 응답을 돌려준다. */
    private static final class RecordingClient extends AiServerClient {

        private final Object response;
        private AiAgent agent;
        private String method;
        private Map<Object, Object> body;

        RecordingClient(Object response) {
            super(WebClient.builder(), "http://ai.test", Duration.ofSeconds(1));
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
