package com.hiremate.global.config;

import com.hiremate.global.AuthenticatedMember;
import java.util.List;
import org.springdoc.core.utils.SpringDocUtils;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    static {
        // 서버가 채우는 인자라 API 문서의 요청 항목에서 뺀다
        SpringDocUtils.getConfig().addRequestWrapperToIgnore(AuthenticatedMember.class);
    }

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new AuthenticatedMemberArgumentResolver());
    }
}
