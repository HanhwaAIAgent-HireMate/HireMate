package com.hiremate.ai.application;

/** Root Agent (Recruitment Orchestrator). 요청을 해석해 실행 계획을 만든다. 지원자를 직접 고르거나 상태를 바꾸지 않는다. */
public interface RootAgent {

    ChatPlan plan(ChatContext context);
}
