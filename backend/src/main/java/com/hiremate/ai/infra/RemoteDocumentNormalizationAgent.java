package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.DocumentNormalizationAgent;
import com.hiremate.apply.DocumentNormalizationRequest;
import com.hiremate.apply.DocumentNormalizationService;
import org.springframework.stereotype.Component;

/** 작업 등록과 요청 스냅샷 저장은 apply 공개 서비스가 문서 잠금 안에서 처리한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.APPLICATION, mode = AiMode.REMOTE)
class RemoteDocumentNormalizationAgent implements DocumentNormalizationAgent {
    private final DocumentNormalizationService documents;

    RemoteDocumentNormalizationAgent(DocumentNormalizationService documents) {
        this.documents = documents;
    }

    @Override
    public void normalize(DocumentNormalizationRequest request) {
        documents.enqueue(request);
    }
}
