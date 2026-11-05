package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatReport;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

/** Chat에서 이전 전형의 결과 리포트를 달라고 하면 저장된 리포트를 연다. Root는 대신 정해 둔 계획을 낸다. */
class StageReportChatTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("다음 전형 Chat에서 이전 전형 리포트를 요청하면 새로 만들지 않고 저장된 리포트를 연다")
    void previousStageReportOpensTheSavedOne() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, "전형은 서류, 1차 면접 순으로 해줘");
        Map<String, Object> form = TestFixtures.form("applicant@example.com", false);
        form.put("name", "지원자1");
        expect(anonymous().multipart(posting.applyPath(), form), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).stream()
                .noneMatch(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE)
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        UUID id = applications.applicants(hr.companyId(), recruitmentId).getFirst().applicationId();
        applications.recordAnalysis(id,
                ApplicationAnalysis.of(3, "OO카드", List.of()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String documentId = closed.path("stages").get(0).path("id").asString();
        String document = "/api/stages/" + documentId;
        expect(hr.post(document + "/decisions", Map.of("applicationIds", List.of(id), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        scheduleNextInterview(hr, document);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String saved = awaitStageReport(hr, document);
        String interview = "/api/stages/" + json(expect(hr.post(document + "/finish", null), 200))
                .path("nextStageId").asString();

        ChatReport previous = new ChatReport(ChatReport.Kind.STAGE, UUID.fromString(documentId), List.of(), "", false,
                null);
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.REPORT, null, null, List.of(),
                "서류 전형 결과 리포트를 열어요.", List.of(), List.of(), List.of(), List.of(), Map.of(), Map.of(),
                false, previous));

        JsonNode chat = done(expect(hr.post(TestFixtures.firstTabPath(hr, interview) + "/chat",
                Map.of("message", "이전 전형 리포트 보여줘", "mentionIds", List.of(), "checkedIds", List.of())), 200));

        assertThat(chat.path("reportId").asString()).isEqualTo(saved);
        // 어느 전형 리포트인지 이름으로 말하고, 답 아래에 리포트를 쓴 Agent를 보여 준다
        assertThat(chat.path("message").asString()).isEqualTo("서류 전형 결과 리포트를 열어요.");
        assertThat(chat.path("agents").toString()).contains("Report Agent");
        assertThat(json(expect(hr.get(document + "/reports"), 200))).hasSize(1);
        expect(hr.get(interview + "/reports/" + saved), 200);
    }

    private static String awaitStageReport(TestApi hr, String stagePath) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            JsonNode list = json(expect(hr.get(stagePath + "/reports"), 200));
            if (!list.isEmpty()) {
                return list.get(0).path("id").asString();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Stage report was not created.");
    }
}
