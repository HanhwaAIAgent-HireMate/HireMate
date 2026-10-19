package com.hiremate.ai.application;

/** 화면에 다시 보여 줄 AI Chat의 지난 턴: 담당자 질문과 그때의 답. */
public record ChatTurn(String message, ChatAnswer answer) {
}
