package com.hiremate;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;

/**
 * 실제 HTTP, PostgreSQL, Redis로 검사하는 업무 API 테스트의 공통 설정. 같은 설정을 써서 컨텍스트를 함께 쓴다.
 * 평가 전형 결과 더미는 끈다. 평가 결과가 없는 상태부터 검사하는 테스트가 있어서다 (켜서 보는 테스트는 DummyAssessmentTests).
 */
@TestPropertySource(properties = "hiremate.dummy.assessment-results.enabled=false")
@Import({TestcontainersConfiguration.class, TestMailConfiguration.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "hiremate.files.local-dir=${java.io.tmpdir}/hiremate-test-files")
public abstract class IntegrationTest {

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
