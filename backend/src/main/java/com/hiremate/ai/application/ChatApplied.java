package com.hiremate.ai.application;

/** 업무 서버가 실제로 반영한 최종 응답. 원본 계획과 질문이 일치하는 대화만 갱신한다. */
public record ChatApplied(String threadId, String message, ChatPlan previous, ChatPlan plan) {
}
