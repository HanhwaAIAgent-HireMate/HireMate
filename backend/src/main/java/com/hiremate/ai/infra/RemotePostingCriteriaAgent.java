package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PostingCriteriaAgent;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Posting Agent에게 서류 평가 기준 초안을 받는다 (posting/draftCriterion, posting/recommendImportant).
 * 요청 본문은 메서드의 매개변수 이름을 키로 한다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.REMOTE)
class RemotePostingCriteriaAgent implements PostingCriteriaAgent {

    private final AiServerClient client;

    RemotePostingCriteriaAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public CriterionDraft draftCriterion(PostingContent posting, ScreeningRubric.Category category, String text,
            String ncsUnitCode) {
        // 참고 NCS 능력단위가 없을 수 있어, null을 넣을 수 없는 Map.of 대신 HashMap을 쓴다
        Map<String, Object> body = new HashMap<>();
        body.put("posting", posting);
        body.put("category", category);
        body.put("text", text);
        body.put("ncsUnitCode", ncsUnitCode);
        return client.post(AiAgent.POSTING, "draftCriterion", body, CriterionDraft.class);
    }

    @Override
    public ImportantAdvice recommendImportant(PostingContent posting) {
        return client.post(AiAgent.POSTING, "recommendImportant", Map.of("posting", posting), ImportantAdvice.class);
    }
}
