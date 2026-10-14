package com.hiremate.auth.config;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** LogoutFilter가 제공하는 실제 엔드포인트를 API 명세에 추가한다. */
@Configuration
public class AuthOpenApiConfig {

    @Bean
    OpenApiCustomizer authLogoutDocumentation() {
        return api -> api.path("/api/auth/logout", new PathItem().post(new Operation()
                .operationId("logout")
                .addTagsItem("auth-controller")
                .summary("Log out and invalidate the session")
                .addParametersItem(new Parameter().in("header").name("X-CSRF-TOKEN").required(true)
                        .schema(new StringSchema()))
                .responses(new ApiResponses()
                        .addApiResponse("204", new ApiResponse().description("Session invalidated"))
                        .addApiResponse("403", new ApiResponse().description("Missing or invalid CSRF token")))));
    }
}
