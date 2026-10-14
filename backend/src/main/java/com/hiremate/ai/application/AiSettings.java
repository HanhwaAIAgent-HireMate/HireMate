package com.hiremate.ai.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** AI 연동 방식. stub이면 backend 안의 개발용 응답을 쓰고, 화면은 응답에 개발용 표시를 단다. */
@Component
public class AiSettings {

    private final boolean stub;

    AiSettings(@Value("${hiremate.ai.mode:stub}") String mode) {
        this.stub = "stub".equalsIgnoreCase(mode);
    }

    public boolean isStub() {
        return stub;
    }
}
