package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Root Agent (POST /agents/root/plan). {@code HIREMATE_AI_AGENTS_ROOT=remote}로 켠다.
 * 계획 가운데 선택 지원자 변경은 ChatService가 screening 모듈로 검증해 실행한다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.ROOT, mode = AiMode.REMOTE)
class RemoteRootAgent implements RootAgent {

    private final AiServerClient client;

    RemoteRootAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public ChatPlan plan(ChatContext context) {
        return client.post(AiAgent.ROOT, "plan", Map.of("context", context), ChatPlan.class);
    }
}
