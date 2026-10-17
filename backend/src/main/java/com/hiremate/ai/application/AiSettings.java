package com.hiremate.ai.application;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/** Agent별 AI 연동 방식. stub이면 backend 안의 개발용 응답을 쓰고, 화면은 응답에 개발용 표시를 단다. */
@Component
public class AiSettings {

    private final Environment environment;

    AiSettings(Environment environment) {
        this.environment = environment;
    }

    public boolean isStub(AiAgent agent) {
        return AiMode.of(environment, agent) == AiMode.STUB;
    }
}
