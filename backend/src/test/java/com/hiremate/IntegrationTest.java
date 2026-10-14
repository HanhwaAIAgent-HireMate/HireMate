package com.hiremate;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;

/** 실제 HTTP, PostgreSQL, Redis로 검사하는 업무 API 테스트의 공통 설정. 같은 설정을 써서 컨텍스트를 함께 쓴다. */
@Import({TestcontainersConfiguration.class, TestMailConfiguration.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "hiremate.files.local-dir=${java.io.tmpdir}/hiremate-test-files")
abstract class IntegrationTest {

    @LocalServerPort
    private int port;

    /** 새 기업과 HR 계정을 만들고 로그인한 클라이언트. */
    protected TestApi newHr() throws Exception {
        TestApi api = anonymous();
        api.signupAndLogin();
        return api;
    }

    protected TestApi anonymous() {
        return new TestApi(port);
    }
}
