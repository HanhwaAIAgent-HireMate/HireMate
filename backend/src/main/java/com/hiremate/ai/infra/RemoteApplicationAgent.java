package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ApplicationAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Application Agent (POST /agents/application/analyze). {@code HIREMATE_AI_AGENTS_APPLICATION=remote}로 켠다.
 * 지원 접수 이벤트에서 부르므로 응답을 hiremate.ai.application-timeout(기본 180초)까지 기다린다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.REMOTE)
class RemoteApplicationAgent implements ApplicationAgent {

    private final AiServerClient client;

    RemoteApplicationAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public ApplicationAnalysis analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric) {
        return client.post(AiAgent.APPLICATION, "analyze",
                Map.of("applicant", applicant, "posting", posting, "rubric", rubric), ApplicationAnalysis.class);
    }
}
