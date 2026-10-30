package com.hiremate.ai.application;

import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import java.util.List;

/**
 * 🎤 꼬리질문 제안 요청 (ai 서버 POST /agents/interview/follow-ups).
 *
 * @param posting 공고. 질문이 직무와 맞는지 보는 기준이다
 * @param chain 처음 질문부터 꼬리질문을 받을 질문까지의 질문과 답 (마지막이 지금 질문)
 * @param avoid [다시 제안]이면 앞서 보여 준 제안. 같은 질문을 다시 내지 않는다. 처음이면 빈 목록
 */
public record InterviewFollowUpsRequest(PostingContent posting, List<InterviewView.Question> chain,
        List<String> avoid) {

    public InterviewFollowUpsRequest {
        chain = List.copyOf(chain);
        avoid = avoid == null ? List.of() : List.copyOf(avoid);
    }
}
