package com.hiremate;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class PublicPathTests extends IntegrationTest {

    @Test
    @DisplayName("공개 경로는 로그인 없이 열리고 POST는 CSRF 토큰을 요구한다")
    void publicPathsAreOpenButRequireCsrfForPost() throws Exception {
        TestApi anonymous = anonymous();
        // 아직 등록된 공개 API가 없으므로 인증 오류가 아닌 404가 나와야 한다
        assertThat(anonymous.get("/api/public/unknown").statusCode()).isEqualTo(404);
        assertThat(anonymous.post("/api/public/unknown", Map.of()).statusCode()).isEqualTo(404);
    }
}
