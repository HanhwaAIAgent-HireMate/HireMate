package com.hiremate.ai;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/** 평가 결과를 등록하면 Assessment Agent가 그 결과로 불리는지 확인한다. Agent는 대신 기록만 하는 가짜다. */
class AssessmentAnalysisTests extends IntegrationTest {

    @MockitoBean
    private AssessmentAgent agent;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("평가 결과를 수동 입력하면 점수 · 등급 · URL · 메모를 그대로 Assessment Agent에 넘기고, 빈 NCS 영역은 null로 둔다")
    void manualResultReachesAssessmentAgent() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 직무역량 평가 순으로 해줘");
        Map<String, Object> form = TestFixtures.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        UUID applicationId = awaitApplicant(hr.companyId(), recruitmentId);
        applications.recordAnalysis(applicationId, new ApplicationAnalysis(3, "OO카드", 90, true));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", List.of(applicationId.toString()), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String stageId = json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();

        Map<String, Object> manual = new HashMap<>();
        manual.put("total", 82.5);
        manual.put("areas", Map.of("의사소통능력", 80, "문제해결능력", 90));
        manual.put("grade", "B");
        manual.put("url", "https://github.com/example/assignment");
        manual.put("note", "코드 구조 설명이 명확했음");
        expect(hr.put("/api/stages/" + stageId + "/assessment/results/" + applicationId, manual), 200);

        ArgumentCaptor<AssessmentInput> sent = ArgumentCaptor.forClass(AssessmentInput.class);
        verify(agent, timeout(10_000)).analyze(sent.capture());
        AssessmentInput input = sent.getValue();
        assertThat(input.companyId()).isEqualTo(hr.companyId());
        assertThat(input.recruitmentId()).isEqualTo(recruitmentId);
        assertThat(input.stageId()).isEqualTo(UUID.fromString(stageId));
        assertThat(input.applicationId()).isEqualTo(applicationId);
        assertThat(input.stageName()).isEqualTo("직무역량 평가");
        assertThat(input.total()).isEqualByComparingTo("82.5");
        assertThat(input.areas()).containsKeys("의사소통능력", "수리능력", "문제해결능력", "정보능력", "기술능력");
        assertThat(input.areas().get("문제해결능력")).isEqualByComparingTo(new BigDecimal("90"));
        assertThat(input.areas().get("수리능력")).isNull();
        assertThat(input.grade()).isEqualTo("B");
        assertThat(input.url()).isEqualTo("https://github.com/example/assignment");
        assertThat(input.note()).isEqualTo("코드 구조 설명이 명확했음");
    }

    private UUID awaitApplicant(UUID companyId, UUID recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            var analyzed = applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.documentScore() != null)
                    .findFirst();
            if (analyzed.isPresent()) {
                return analyzed.get().applicationId();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }
}
