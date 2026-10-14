package com.hiremate.ai.application;

import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingSuggestion;

/**
 * Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 게시는 하지 않는다.
 * 문서를 고치는 요청만 받고, 수정안은 HR이 적용 여부를 정한다.
 */
public interface PostingAgent {

    Result revise(PostingDraftContext posting, String writingStyle, String request);

    /**
     * @param reply Chat에 보여 줄 답
     * @param suggestion 수정안. 되묻거나 처리할 수 없는 요청이면 null
     */
    record Result(String reply, PostingSuggestion suggestion) {
    }
}
