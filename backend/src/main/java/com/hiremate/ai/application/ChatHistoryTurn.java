package com.hiremate.ai.application;

/**
 * ai 서버가 보관한 대화방의 지난 턴 하나.
 *
 * @param plan 그때의 계획. message의 {count}는 대상 수, {total}은 total로 바꿔 보여 준다
 * @param total 그때 전형 인원
 */
public record ChatHistoryTurn(String message, ChatPlan plan, int total) {
}
