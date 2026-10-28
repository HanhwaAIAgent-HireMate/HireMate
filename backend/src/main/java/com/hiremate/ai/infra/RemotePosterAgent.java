package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PosterAgent;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterProposal;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.REMOTE)
class RemotePosterAgent implements PosterAgent {
    private final AiServerClient client;

    RemotePosterAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public PosterProposal design(PosterContext context, String request) {
        return client.post(AiAgent.POSTING, "design", Map.of("context", context, "request", request),
                PosterProposal.class);
    }
}
