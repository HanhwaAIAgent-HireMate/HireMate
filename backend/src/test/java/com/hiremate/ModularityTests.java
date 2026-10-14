package com.hiremate;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

/**
 * 모듈 경계를 검사한다. 모듈 사이에 순환 의존이 없고, 다른 모듈의 하위 패키지를 직접 쓰지 않아야 통과한다.
 */
class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(HireMateApplication.class).verify();
    }
}
