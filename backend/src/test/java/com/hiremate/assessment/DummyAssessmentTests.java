package com.hiremate.assessment;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.math.BigDecimal;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;
import tools.jackson.databind.JsonNode;

/** 서류 전형을 종료해 평가 전형이 시작되면 넘어온 합격자 모두에게 더미 인적성 결과가 입혀지는지 확인한다. */
@TestPropertySource(properties = "hiremate.dummy.assessment-results.enabled=true")
class DummyAssessmentTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("평가 전형이 시작되면 서류 합격자에게만 결과가 들어가고, 더미 결과표에 있으면 그 값을, 없으면 만든 점수를 쓴다")
    void dummyResultsForPassedApplicants() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 직무역량 평가 순으로 해줘");
        // 김도현 · 이서윤은 더미 결과표에 있고, 외부인은 없다
        for (String email : List.of("dohyun.kim@example.com", "seoyun.lee@example.com", "outsider@example.com")) {
            expect(anonymous().multipart(posting.applyPath(), TestFixtures.form(email, false)), 201);
        }
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Map<String, UUID> ids = awaitApplicants(hr.companyId(), recruitmentId, 3);
        ids.values().forEach(id -> applications.recordAnalysis(id,
                ApplicationAnalysis.of(3, "OO카드", List.of())));

        // 김도현 · 외부인은 서류 합격, 이서윤은 불합격
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions", Map.of("applicationIds",
                List.of(ids.get("dohyun.kim@example.com").toString(), ids.get("outsider@example.com").toString()),
                "decision", "PASS")), 204);
        expect(hr.post(document + "/decisions", Map.of("applicationIds",
                List.of(ids.get("seoyun.lee@example.com").toString()), "decision", "FAIL")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        expect(hr.post(document + "/notices/FAIL/send", null), 200);
        String stageId = json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();
        String results = "/api/stages/" + stageId + "/assessment/results/";

        JsonNode dohyun = awaitResult(hr, results + ids.get("dohyun.kim@example.com"));
        assertThat(dohyun.path("total").decimalValue()).isEqualByComparingTo("93.8");
        assertThat(dohyun.path("grade").asString()).isEqualTo("A");
        assertThat(dohyun.path("areas").path("문제해결능력").decimalValue()).isEqualByComparingTo("96");
        // 결과표에 없는 합격자도 NCS 5개 영역 점수와 총점 · 등급을 받는다
        JsonNode outsider = awaitResult(hr, results + ids.get("outsider@example.com"));
        assertThat(outsider.path("areas").size()).isEqualTo(5);
        assertThat(outsider.path("total").decimalValue()).isBetween(new BigDecimal("55"), new BigDecimal("98"));
        assertThat(outsider.path("grade").asString()).isIn("A", "B", "C", "D");
        // 평가 전형 대상이 아닌 불합격자에게는 넣지 않는다
        assertThat(hr.get(results + ids.get("seoyun.lee@example.com")).statusCode()).isIn(404, 409);
    }

    private Map<String, UUID> awaitApplicants(UUID companyId, UUID recruitmentId, int count)
            throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            List<ApplicantInfo> analyzed = applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
                    .toList();
            if (analyzed.size() == count) {
                return analyzed.stream().collect(Collectors.toMap(ApplicantInfo::email, ApplicantInfo::applicationId));
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }

    private static JsonNode awaitResult(TestApi hr, String path) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            HttpResponse<String> response = hr.get(path);
            if (response.statusCode() == 200) {
                return json(response);
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Dummy assessment result was not added.");
    }
}
