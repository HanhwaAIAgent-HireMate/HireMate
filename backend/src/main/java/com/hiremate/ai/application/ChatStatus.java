package com.hiremate.ai.application;

/** Chat 처리 단계 문구. SSE status 이벤트의 data다. 문구는 코드 상수다 (모델이 쓴 문장이 아니다). */
public record ChatStatus(String text) {
}
