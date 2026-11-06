package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.DocumentNormalizationAgent;
import com.hiremate.apply.DocumentNormalizationRequest;
import org.springframework.stereotype.Component;

/** 개발 모드에서는 LLM 정리를 맡기거나 가짜 정제 JSON을 저장하지 않는다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.STUB)
class StubDocumentNormalizationAgent implements DocumentNormalizationAgent {
    @Override
    public void normalize(DocumentNormalizationRequest request) {
        // 개발 모드는 파서 원문만 사용한다.
    }
}
