package com.hiremate.ai.application;

import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import com.hiremate.posting.PostingSuggestion;

/**
 * Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 게시는 하지 않는다.
 * 문서를 고치는 요청만 받고, 수정안은 HR이 적용 여부를 정한다.
 */
public interface PostingAgent {

    /**
     * HR의 요청대로 공고 수정안을 만든다.
     *
     * @param posting 저장된 지금 공고
     * @param writingStyle 기업의 공고 작성 스타일
     * @param request HR의 수정 요청
     * @param focus HR이 고른 줄. 고르면 그 줄만 고치고, 고르지 않았으면 null이다
     * @return Chat에 보여 줄 답과 수정안
     */
    Result revise(PostingDraftContext posting, String writingStyle, String request, PostingFocus focus);

    /**
     * @param reply Chat에 보여 줄 답
     * @param suggestion 수정안. 되묻거나 처리할 수 없는 요청이면 null
     */
    record Result(String reply, PostingSuggestion suggestion) {
    }
}
