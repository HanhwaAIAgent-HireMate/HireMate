package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ChatApplied;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.RootAgent;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Root Agent (POST /agents/root/plan, SSE). {@code HIREMATE_AI_AGENTS_ROOT=remote}로 켠다.
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
    public ChatPlan plan(ChatContext context, ChatProgress progress) {
        return client.stream(AiAgent.ROOT, "plan", Map.of("context", context), ChatPlan.class, progress);
    }

    @Override
    public void applied(ChatApplied applied) {
        client.post(AiAgent.ROOT, "applied", Map.of("applied", applied), Map.class);
    }

    @Override
    public List<ChatHistoryTurn> history(String threadId) {
        return client.post(AiAgent.ROOT, "history", Map.of("threadId", threadId),
                new ParameterizedTypeReference<List<ChatHistoryTurn>>() { });
    }

    @Override
    public void forget(String threadId) {
        client.post(AiAgent.ROOT, "forget", Map.of("threadId", threadId), Map.class);
    }

    @Override
    public Optional<String> title(String message, String reply) {
        return Optional.ofNullable(client.post(AiAgent.ROOT, "title", Map.of("message", message, "reply", reply),
                Title.class).title());
    }

    /** /agents/root/title 응답. 제목을 만들지 못하면 null이다. */
    private record Title(String title) {
    }
}
