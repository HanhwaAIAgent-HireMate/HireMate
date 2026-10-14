package com.hiremate.global.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/** 모듈 간 비동기 이벤트(@ApplicationModuleListener)와 예약 작업(공고 자동 마감 등)을 켠다. */
@Configuration
@EnableAsync
@EnableScheduling
public class AsyncConfig {
}
