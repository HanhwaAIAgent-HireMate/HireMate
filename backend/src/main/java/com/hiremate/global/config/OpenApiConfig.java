package com.hiremate.global.config;

import io.swagger.v3.oas.models.media.Schema;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    /**
     * 모든 속성을 required로 표시한다. 서버는 항목을 빼지 않고 값이 없으면 null을 보내므로, frontend 타입이
     * 선택 항목(?)으로 생성되지 않게 한다. null이 올 수 있는 항목은 {@code @Schema(nullable = true)}로 표시한다.
     */
    @Bean
    OpenApiCustomizer requiredPropertiesCustomizer() {
        return openApi -> {
            if (openApi.getComponents() == null || openApi.getComponents().getSchemas() == null) {
                return;
            }
            openApi.getComponents().getSchemas().values().forEach(OpenApiConfig::requireAll);
        };
    }

    private static void requireAll(Schema<?> schema) {
        Map<String, ?> properties = schema.getProperties();
        if (properties == null) {
            return;
        }
        for (String name : List.copyOf(properties.keySet())) {
            Schema<?> property = schema.getProperties().get(name);
            // null이 올 수 있는 객체 참조는 $ref 옆의 type이 무시되므로 oneOf로 바꾼다
            if (property.get$ref() != null && property.getTypes() != null && property.getTypes().contains("null")) {
                schema.getProperties().put(name, new Schema<>().oneOf(
                        List.of(new Schema<>().$ref(property.get$ref()), new Schema<>().types(Set.of("null")))));
            }
        }
        List<String> required = new ArrayList<>(schema.getRequired() == null ? List.of() : schema.getRequired());
        properties.keySet().stream().filter(name -> !required.contains(name)).forEach(required::add);
        schema.setRequired(required);
    }
}
