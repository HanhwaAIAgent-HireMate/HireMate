package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import java.util.Map;
import java.util.Objects;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

/** {@link ConditionalOnAiMode}의 조건. 설정에서 Agent의 연동 방식을 읽어 비교한다. */
class AiModeCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        Map<String, Object> attributes = Objects.requireNonNull(
                metadata.getAnnotationAttributes(ConditionalOnAiMode.class.getName()));
        AiAgent agent = (AiAgent) attributes.get("agent");
        AiMode mode = (AiMode) attributes.get("mode");
        return AiMode.of(context.getEnvironment(), agent) == mode;
    }
}
