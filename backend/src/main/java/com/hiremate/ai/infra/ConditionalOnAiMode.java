package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

/**
 * Agent의 연동 방식이 mode일 때만 빈으로 등록한다. stub 구현은 STUB, ai 서버를 부르는 Remote 구현은 REMOTE로 단다.
 * Agent마다 따로 바꿀 수 있어 한 Agent를 remote로 켜도 다른 Agent의 stub은 그대로 쓴다.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Conditional(AiModeCondition.class)
@interface ConditionalOnAiMode {

    AiAgent agent();

    AiMode mode();
}
