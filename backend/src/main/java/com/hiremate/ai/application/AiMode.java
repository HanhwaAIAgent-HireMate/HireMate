package com.hiremate.ai.application;

import java.util.Locale;
import org.springframework.core.env.PropertyResolver;

/** AI 연동 방식. stub은 backend 안의 개발용 응답, remote는 ai 서버(ai/) 호출이다. */
public enum AiMode {
    STUB,
    REMOTE;

    /** hiremate.ai.agents.{key}가 있으면 그 값을, 없으면 hiremate.ai.mode를 쓴다. 둘 다 없으면 stub이다. */
    public static AiMode of(PropertyResolver properties, AiAgent agent) {
        String value = properties.getProperty("hiremate.ai.agents." + agent.key(),
                properties.getProperty("hiremate.ai.mode", "stub"));
        return switch (value.strip().toLowerCase(Locale.ROOT)) {
            case "stub" -> STUB;
            case "remote" -> REMOTE;
            default -> throw new IllegalStateException("Unknown AI mode '" + value + "' for " + agent.key());
        };
    }
}
