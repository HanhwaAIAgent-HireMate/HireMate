package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.PostingAgent;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 Posting Agent를 부른다. 요청 본문은 revise의 매개변수 이름(posting, writingStyle, request, focus)을 키로 한다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.REMOTE)
class RemotePostingAgent implements PostingAgent {

    private final AiServerClient client;

    RemotePostingAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public Result revise(PostingDraftContext posting, String writingStyle, String request, PostingFocus focus,
            ChatProgress progress) {
        // 공고 작성 스타일을 등록하지 않은 기업이 있고 고른 줄은 없을 수 있어, null을 넣을 수 없는 Map.of 대신 HashMap을 쓴다
        Map<String, Object> body = new HashMap<>();
        body.put("posting", posting);
        body.put("writingStyle", writingStyle == null ? "" : writingStyle);
        body.put("request", request);
        body.put("focus", focus);
        return client.stream(AiAgent.POSTING, "revise", body, Result.class, progress);
    }
}
