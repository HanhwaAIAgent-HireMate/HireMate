package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import com.hiremate.report.AgentReportKind;
import com.hiremate.report.AgentReportService;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Report Agent 리포트: 비교 요청, 결과 확정 때 전형 결과 리포트, AI 워커 결과 저장. 테스트는 개발용 Agent로 돈다. */
class AgentReportTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Autowired
    private AgentReportService reports;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JsonMapper json;

    @Value("${hiremate.jobs.result-stream}")
    private String resultStream;

    @Test
    @DisplayName("선택 지원자 비교 리포트는 묶음에 이름 없이 지원자번호만 넣고, 화면에 줄 때 이름을 붙인다")
    void compareReportKeepsNamesOutOfTheBundle() throws Exception {
        Stage stage = startDocumentStage(3);
        JsonNode requested = json(expect(stage.hr().post(stage.path() + "/reports/compare",
                Map.of("applicationIds", stage.ids().subList(0, 2), "focus", "협업", "brief", true)), 202));
        String reportId = requested.path("reportId").asString();

        JsonNode report = json(expect(stage.hr().get(stage.path() + "/reports/" + reportId), 200));
        assertThat(report.path("kind").asString()).isEqualTo("COMPARE");
        assertThat(report.path("status").asString()).isEqualTo("DONE");
        JsonNode bundle = report.path("bundle");
        assertThat(bundle.path("focus").asString()).isEqualTo("협업");
        assertThat(bundle.path("brief").asBoolean()).isTrue();
        assertThat(bundle.path("targets")).hasSize(2);
        assertThat(bundle.toString()).doesNotContain("지원자1").doesNotContain("applicant1@example.com");
        String first = bundle.path("targets").get(0).asString();
        assertThat(first).matches("A-\\d{4}");
        assertThat(report.path("names").path(first).asString()).startsWith("지원자");
        assertThat(report.path("report").path("spec").path("sections")).isNotEmpty();

        expect(newHr().get(stage.path() + "/reports/" + reportId), 404);
        expect(stage.hr().post(stage.path() + "/reports/compare",
                Map.of("applicationIds", stage.ids().subList(0, 1), "focus", "", "brief", false)), 400);
    }

    @Test
    @DisplayName("전형 결과를 확정하면 전형 결과 리포트가 만들어지고, 안내를 모두 보내면 열린다. 서류 점수 대신 필수 조건 지표를 넣는다")
    void confirmingStageComposesStageReport() throws Exception {
        Stage stage = startDocumentStage(3);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")), 204);
        expect(stage.hr().post(stage.path() + "/confirm", null), 200);

        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        JsonNode list = json(expect(stage.hr().get(stage.path() + "/reports"), 200));
        while (list.isEmpty() && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
            list = json(expect(stage.hr().get(stage.path() + "/reports"), 200));
        }
        assertThat(list).hasSize(1);
        assertThat(list.get(0).path("kind").asString()).isEqualTo("STAGE");
        String path = stage.path() + "/reports/" + list.get(0).path("id").asString();
        expect(stage.hr().get(path), 409);
        expect(stage.hr().post(stage.path() + "/notices/prepare", null), 200);
        expect(stage.hr().post(stage.path() + "/notices/PASS/send", null), 200);
        expect(stage.hr().post(stage.path() + "/notices/FAIL/send", null), 200);
        JsonNode report = json(expect(stage.hr().get(path), 200));
        JsonNode metrics = report.path("bundle").path("metrics");
        assertThat(metrics.findValuesAsString("id"))
                .contains("m-target", "m-pass", "m-pass-rate", "m-req-met", "m-req-unmet", "m-req-unknown");
        JsonNode bundle = report.path("bundle");
        assertThat(bundle.path("areas")).isNotEmpty();
        assertThat(bundle.hasNonNull("totalKey")).isFalse();
        assertThat(bundle.path("areas")).allMatch(area -> !area.hasNonNull("scoreKey"));
        assertThat(bundle.path("facts").findValuesAsString("key"))
                .doesNotContain("document.total", "document.qualification", "document.preference");
    }

    @Test
    @DisplayName("서류 전형 분포는 전형 지원자 전원을 바로 세고, 목표 인원은 요청마다 바꿔 저장하지 않는다")
    void documentStageDistributionCountsEveryApplicant() throws Exception {
        Stage stage = startDocumentStage(3);

        JsonNode first = json(expect(stage.hr().get(stage.path() + "/reports/distribution"), 200));
        assertThat(first.path("total").asInt()).isEqualTo(3);
        assertThat(first.path("target").asInt()).isEqualTo(first.path("defaultTarget").asInt())
                .isEqualTo(first.path("hireCount").asInt() * first.path("targetMultiplier").asInt());
        assertThat(first.path("criteria")).isNotEmpty();
        assertThat(first.path("groups").findValuesAsString("id")).contains("below-line");

        JsonNode changed = json(expect(stage.hr().get(stage.path() + "/reports/distribution?target=1"), 200));
        assertThat(changed.path("target").asInt()).isEqualTo(1);
        JsonNode again = json(expect(stage.hr().get(stage.path() + "/reports/distribution"), 200));
        assertThat(again.path("target").asInt()).isEqualTo(first.path("defaultTarget").asInt());
    }

    @Test
    @DisplayName("평가 전형 리포트 묶음은 평가 전형을 영역으로 넣어, 영역 점수 key와 총점 key를 함께 준다")
    void assessmentStageBundleHasAssessmentArea() throws Exception {
        Stage document = startDocumentStage(2, "전형은 서류, 직무역량 평가 순으로 해줘");
        TestApi hr = document.hr();
        expect(hr.post(document.path() + "/decisions",
                Map.of("applicationIds", document.ids(), "decision", "PASS")), 204);
        expect(hr.post(document.path() + "/confirm", null), 200);
        expect(hr.post(document.path() + "/notices/prepare", null), 200);
        expect(hr.post(document.path() + "/notices/PASS/send", null), 200);
        String stageId = json(expect(hr.post(document.path() + "/finish", null), 200)).path("nextStageId").asString();
        Stage assessment = new Stage(hr, stageId, document.ids());
        for (String applicationId : assessment.ids()) {
            expect(hr.put(assessment.path() + "/assessment/results/" + applicationId,
                    Map.of("total", 80, "areas", Map.of("의사소통능력", 70, "문제해결능력", 90))), 200);
        }

        JsonNode requested = json(expect(hr.post(assessment.path() + "/reports/compare",
                Map.of("applicationIds", assessment.ids(), "focus", "", "brief", false)), 202));
        JsonNode bundle = json(expect(hr.get(assessment.path() + "/reports/" + requested.path("reportId").asString()),
                200)).path("bundle");

        assertThat(bundle.path("totalKey").asString()).isEqualTo("assessment.total");
        JsonNode areas = bundle.path("areas");
        assertThat(areas).hasSize(1);
        assertThat(areas.get(0).path("id").asString()).isEqualTo("assessment");
        assertThat(areas.get(0).path("scoreKey").asString()).isEqualTo("assessment.total");
        assertThat(areas.get(0).path("keys").toString())
                .contains("assessment.area.의사소통능력", "assessment.area.문제해결능력");
    }

    @Test
    @DisplayName("AI 워커가 쓴 부품 설계서를 리포트에 저장하고, 실패하면 실패로 둔다")
    void savesWorkerResults() throws Exception {
        Stage stage = startDocumentStage(2);
        UUID stageId = UUID.fromString(stage.stageId());
        UUID recruitmentId = UUID.fromString(json(expect(stage.hr().get(stage.path()), 200))
                .path("recruitmentId").asString());
        UUID done = reports.start(stage.hr().companyId(), recruitmentId, stageId, AgentReportKind.COMPARE, null, "",
                false, "{}");
        UUID failed = reports.start(stage.hr().companyId(), recruitmentId, stageId, AgentReportKind.COMPARE, null,
                "", false, "{}");
        JsonNode composed = json.readTree("""
                {"spec": {"title": "비교", "summary": "요약이에요.", "skills": [], "sections": []},
                 "skills": ["compare"], "fallback": false,
                 "bundle": null}""");
        push(new JobResult(UUID.randomUUID(), "report/compose", done.toString(), JobStatus.DONE, composed, null));
        push(new JobResult(UUID.randomUUID(), "report/compose", failed.toString(), JobStatus.FAILED, null, "시간 초과"));

        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)
                && (reports.view(stage.hr().companyId(), done).result() == null
                        || reports.view(stage.hr().companyId(), failed).error() == null)) {
            Thread.sleep(200);
        }
        var saved = reports.view(stage.hr().companyId(), done);
        assertThat(saved.status().name()).isEqualTo("DONE");
        assertThat(json.readTree(saved.result()).path("skills").get(0).asString()).isEqualTo("compare");
        assertThat(reports.view(stage.hr().companyId(), failed).status().name()).isEqualTo("FAILED");
    }

    private void push(JobResult result) {
        redis.opsForStream().add(StreamRecords.string(Map.of("result", json.writeValueAsString(result)))
                .withStreamKey(resultStream));
    }

    private Stage startDocumentStage(int applicants) throws Exception {
        return startDocumentStage(applicants, null);
    }

    private Stage startDocumentStage(int applicants, String stagePlan) throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, stagePlan);
        for (int i = 1; i <= applicants; i++) {
            Map<String, Object> form = TestFixtures.form("applicant" + i + "@example.com", false);
            form.put("name", "지원자" + i);
            expect(anonymous().multipart(posting.applyPath(), form), 201);
        }
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        awaitAnalyzed(hr.companyId(), recruitmentId, applicants);
        for (var applicant : applications.applicants(hr.companyId(), recruitmentId)) {
            int order = Integer.parseInt(applicant.name().replace("지원자", ""));
            applications.recordAnalysis(applicant.applicationId(), ApplicationAnalysis.of(order, "OO카드",
                    BigDecimal.valueOf(100 - order * 10), true, false, List.of()));
        }
        List<String> ids = applications.applicants(hr.companyId(), recruitmentId).stream()
                .sorted(Comparator.comparing(applicant -> applicant.name()))
                .map(applicant -> applicant.applicationId().toString()).toList();
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        return new Stage(hr, closed.path("stages").get(0).path("id").asString(), ids);
    }

    private void awaitAnalyzed(UUID companyId, UUID recruitmentId, int count) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            if (applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.documentScore() != null).count() == count) {
                return;
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }

    record Stage(TestApi hr, String stageId, List<String> ids) {

        String path() {
            return "/api/stages/" + stageId;
        }
    }
}
