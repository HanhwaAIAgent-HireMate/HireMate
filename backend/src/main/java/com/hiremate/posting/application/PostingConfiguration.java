package com.hiremate.posting.application;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/** 공고 모듈 설정. 서류 평가 기준 더미를 읽는다. */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DummyScreeningRubric.class)
class PostingConfiguration {
}
