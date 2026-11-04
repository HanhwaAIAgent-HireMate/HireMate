package com.hiremate.ai.application;

import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewerRole;
import io.swagger.v3.oas.annotations.media.Schema;

/**
 * NCS를 참고한 Chat 요청의 질문 (ai 응답). ncsCited는 판정을 통과한 NCS 원문을 인용했는가다. 카드에는
 * {@link #draft()}만 넣는다.
 */
public record CitedQuestionDraft(String text, @Schema(nullable = true) String reason,
        @Schema(nullable = true) InterviewerRole interviewerRole, boolean ncsCited) {

    public InterviewQuestionDraft draft() {
        return new InterviewQuestionDraft(text, reason, interviewerRole);
    }
}
