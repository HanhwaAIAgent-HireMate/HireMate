package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import java.util.Map;
import org.springframework.stereotype.Component;

/** ai 서버의 Assessment Agent. 점수 · 등급은 보내기만 하고, ai 서버가 강점 · 약점과 근거를 지원자 프로필에 저장한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.ASSESSMENT, mode = AiMode.REMOTE)
class RemoteAssessmentAgent implements AssessmentAgent {

    private final AiServerClient client;

    RemoteAssessmentAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public AnalyzeResult analyze(AssessmentInput input) {
        return client.post(AiAgent.ASSESSMENT, "analyze", Map.of("input", input), AnalyzeResult.class);
    }
}
