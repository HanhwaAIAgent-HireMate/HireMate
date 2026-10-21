package com.hiremate.ai.application;

/**
 * backend가 부르는 AI Agent. key는 Agent별 연동 설정(hiremate.ai.agents.{key})과 ai 서버 경로(/agents/{key}/{method})에 쓴다.
 */
public enum AiAgent {
    ROOT("root"),
    APPLICATION("application"),
    CANDIDATE_ANALYST("candidate-analyst"),
    ASSESSMENT("assessment"),
    INTERVIEW("interview"),
    POSTING("posting"),
    COMMUNICATION("communication"),
    REPORT("report");

    private final String key;

    AiAgent(String key) {
        this.key = key;
    }

    public String key() {
        return key;
    }
}
