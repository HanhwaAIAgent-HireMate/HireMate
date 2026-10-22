package com.hiremate.global.config;

import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** AI Chat 스트림을 응답하는 동안 Root 호출과 반영을 돌리는 실행기. 요청마다 가상 스레드 하나다. */
@Configuration
public class ChatExecutorConfig {

    @Bean(destroyMethod = "close")
    public Executor chatExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
