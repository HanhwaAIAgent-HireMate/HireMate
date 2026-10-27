package com.hiremate.interview;

import io.swagger.v3.oas.annotations.media.Schema;

/** AI가 생성한 질문과 생성 시 선택한 자료·확인 목적. 과거 질문의 근거를 사후에 추측하지 않는다. */
public record InterviewQuestionDraft(String text, @Schema(nullable = true) String reason) {
}
