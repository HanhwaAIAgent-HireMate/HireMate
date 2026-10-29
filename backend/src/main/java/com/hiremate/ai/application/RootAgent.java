package com.hiremate.ai.application;

import java.util.List;
import java.util.Optional;

/** Root Agent (Recruitment Orchestrator). 요청을 해석해 실행 계획을 만든다. 지원자를 직접 고르거나 상태를 바꾸지 않는다. */
public interface RootAgent {

    /** 계획을 낸다. 처리 중 단계와 검증된 항목은 progress로 먼저 보낸다. */
    ChatPlan plan(ChatContext context, ChatProgress progress);

    /** 검증과 업무 반영을 마친 최종 계획으로 해당 대화 기록을 갱신한다. */
    void applied(ChatApplied applied);

    /** 대화방의 지난 턴. 대화방이 없으면 빈 목록이다. */
    List<ChatHistoryTurn> history(String threadId);

    /** 대화방 하나를 지운다 (탭 지우기). */
    void forget(String threadId);

    /** 탭의 첫 질문과 답으로 탭 이름을 짓는다. 차별 조건 질문이거나 만들지 못하면 빈 값이다. */
    Optional<String> title(String message, String reply);
}
