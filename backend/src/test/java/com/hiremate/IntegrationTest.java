package com.hiremate;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
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

    protected static final String INTERVIEWER_PASSWORD = "interviewer-password-2026";

    @LocalServerPort
    private int port;

    @Autowired
    private ApplicationService applicationService;

    /** 새 기업과 HR 계정을 만들고 로그인한 클라이언트. */
    protected TestApi newHr() throws Exception {
        TestApi api = anonymous();
        api.signupAndLogin();
        return api;
    }

    /** HR이 설정 › 면접관에서 면접관 계정을 만들고 그 계정으로 로그인한 클라이언트. */
    protected TestApi newInterviewer(TestApi hr, String name) throws Exception {
        String email = "interviewer-" + UUID.randomUUID() + "@example.com";
        TestApi.expect(hr.post("/api/companies/me/interviewers",
                Map.of("name", name, "email", email, "password", INTERVIEWER_PASSWORD)), 201);
        TestApi interviewer = anonymous();
        interviewer.login(email, INTERVIEWER_PASSWORD);
        return interviewer;
    }

    protected TestApi anonymous() {
        return new TestApi(port);
    }

    /** 진행 중인 면접 전형 하나. stage는 전형 경로(/api/stages/{id})다. */
    protected record Interview(TestApi hr, UUID recruitmentId, UUID stageId, String stage, UUID applicationId) {

        public String candidate() {
            return stage + "/candidates/" + applicationId;
        }
    }

    /** 서류 합격자 한 명이 있는 진행 중 1차 면접. */
    protected Interview interviewStage() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        expect(anonymous().multipart(posting.applyPath(),
                TestFixtures.form("applicant-" + UUID.randomUUID() + "@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = awaitAnalyzed(hr.companyId(), recruitmentId);
        String document = "/api/stages/" + json(expect(hr.post("/api/recruitments/" + recruitmentId
                + "/posting/close", null), 200)).path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", List.of(applicationId.toString()), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        UUID stageId = UUID.fromString(json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId")
                .asString());
        return new Interview(hr, recruitmentId, stageId, "/api/stages/" + stageId, applicationId);
    }

    private UUID awaitAnalyzed(UUID companyId, UUID recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            var analyzed = applicationService.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
                    .map(ApplicantInfo::applicationId)
                    .findFirst();
            if (analyzed.isPresent()) {
                return analyzed.get();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }
}
