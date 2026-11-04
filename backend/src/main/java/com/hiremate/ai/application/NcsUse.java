package com.hiremate.ai.application;

/**
 * Chat 면접 질문을 만들 때 NCS를 참고할지. Root 계획이 정한다. REQUESTED는 HR이 NCS를 참고하라고 한 요청이라, 인용한 질문이
 * 없으면 Chat 답에 알린다. HELPFUL은 직무 지식 질문에 도움이 될 때 참고한다. SKIP이면 지금처럼 만든다.
 */
public enum NcsUse {
    SKIP,
    REQUESTED,
    HELPFUL
}
