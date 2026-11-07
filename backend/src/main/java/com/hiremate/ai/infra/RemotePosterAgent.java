package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PosterAgent;
import com.hiremate.company.CanvaConnectionService.CanvaRegion;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterProposal;
import java.util.List;
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

    @Override
    public PosterProposal generate(PosterContext context, String request) {
        return client.post(AiAgent.POSTING, "design", Map.of("context", context, "request", request,
                "generateOnly", true), PosterProposal.class);
    }

    @Override
    public CanvaMapping mapCanva(List<CanvaRegion> regions) {
        return client.post(AiAgent.POSTING, "map-canva", Map.of("regions", regions), CanvaMapping.class);
    }

    @Override
    public TemplateLayout templateLayout(List<LayoutRegion> regions) {
        return client.post(AiAgent.POSTING, "template-layout", Map.of("regions", regions), TemplateLayout.class);
    }
}
