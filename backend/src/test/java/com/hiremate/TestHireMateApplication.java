package com.hiremate;

import org.springframework.boot.SpringApplication;

/**
 * Testcontainers로 PostgreSQL과 Redis를 띄워 앱을 실행한다. 로컬 compose 포트와 겹치지 않는다.
 * {@code ./gradlew bootTestRun --args='--server.port=8090 --spring.docker.compose.enabled=false'}
 */
public class TestHireMateApplication {

    public static void main(String[] args) {
        SpringApplication.from(HireMateApplication::main).with(TestcontainersConfiguration.class).run(args);
    }
}
