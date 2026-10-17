package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CommunicationAgent;
import com.hiremate.notice.NoticeDraftContext;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/** ai 서버의 Communication Agent를 부른다. 요청 본문은 write의 매개변수 이름(notice, request)을 키로 한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.COMMUNICATION, mode = AiMode.REMOTE)
class RemoteCommunicationAgent implements CommunicationAgent {

    private final AiServerClient client;

    RemoteCommunicationAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public Draft write(NoticeDraftContext notice, String request) {
        // 처음 초안을 쓸 때 request는 null이라, null을 넣을 수 없는 Map.of 대신 HashMap을 쓴다
        Map<String, Object> body = new HashMap<>();
        body.put("notice", notice);
        body.put("request", request);
        return client.post(AiAgent.COMMUNICATION, "write", body, Draft.class);
    }
}
