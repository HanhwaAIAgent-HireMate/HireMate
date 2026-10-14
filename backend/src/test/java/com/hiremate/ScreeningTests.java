package com.hiremate;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class ScreeningTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("마감하면 지원자 전원이 첫 전형 대상이 되고, 서류 점수 순으로 기준선 위아래가 나뉜다")
    void documentStageListsApplicantsByScore() throws Exception {
        Stage stage = startDocumentStage(4);
        JsonNode list = json(expect(stage.hr().get(stage.path() + "/candidates"), 200));
        assertThat(list.path("total").asLong()).isEqualTo(4);
        assertThat(list.path("items").get(0).path("aboveLine").asBoolean()).isTrue();
        assertThat(list.path("items").get(3).path("aboveLine").asBoolean()).isFalse();

        JsonNode overview = json(expect(stage.hr().get(stage.path()), 200));
        assertThat(overview.path("type").asString()).isEqualTo("DOCUMENT");
        assertThat(overview.path("counts").path("pending").asLong()).isEqualTo(4);
        assertThat(overview.path("steps").get(0).path("targetCount").asLong()).isEqualTo(4);
    }

    @Test
    @DisplayName("기준 미달 지원자는 ↑로 올린 뒤에만 넣고, 빼기는 결정이 아니다")
    void belowLineNeedsPromotionBeforeAdding() throws Exception {
        Stage stage = startDocumentStage(3);
        String below = stage.ids().get(2);
        expect(stage.hr().post(stage.path() + "/selection/add", Map.of("applicationIds", List.of(below))), 409);
        expect(stage.hr().post(stage.path() + "/candidates/" + below + "/promote", null), 204);
        expect(stage.hr().post(stage.path() + "/selection/add", Map.of("applicationIds", List.of(below))), 204);

        JsonNode selection = json(expect(stage.hr().get(stage.path() + "/selection"), 200));
        assertThat(selection.path("total").asLong()).isEqualTo(1);
        assertThat(selection.path("items").get(0).path("aiSelected").asBoolean()).isFalse();

        expect(stage.hr().post(stage.path() + "/selection/remove", Map.of("applicationIds", List.of(below))), 204);
        JsonNode row = json(expect(stage.hr().get(stage.path() + "/candidates?query=지원자3"), 200)).path("items").get(0);
        assertThat(row.path("decision").asString()).isEqualTo("PENDING");
        assertThat(row.path("selected").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("결정하면 선택 지원자에서 빠지고, 되돌리면 돌아오며, 확정하면 미결정은 불합격이 된다")
    void decisionsAndConfirmation() throws Exception {
        Stage stage = startDocumentStage(3);
        List<String> top = stage.ids().subList(0, 2);
        expect(stage.hr().post(stage.path() + "/selection/add", Map.of("applicationIds", top)), 204);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(top.get(0)), "decision", "PASS")), 204);
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(1);

        expect(stage.hr().post(stage.path() + "/decisions/revert", Map.of("applicationIds", List.of(top.get(0)))),
                204);
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(2);

        expect(stage.hr().post(stage.path() + "/decisions", Map.of("applicationIds", top, "decision", "PASS")), 204);
        JsonNode counts = json(expect(stage.hr().post(stage.path() + "/confirm", null), 200));
        assertThat(counts.path("pass").asLong()).isEqualTo(2);
        assertThat(counts.path("pending").asLong()).isEqualTo(1);

        JsonNode after = json(expect(stage.hr().get(stage.path()), 200));
        assertThat(after.path("status").asString()).isEqualTo("CONFIRMED");
        assertThat(after.path("counts").path("fail").asLong()).isEqualTo(1);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(top.get(0)), "decision", "FAIL")), 409);
        expect(stage.hr().post(stage.path() + "/confirm", null), 409);

        JsonNode finished = json(expect(stage.hr().post(stage.path() + "/finish", null), 200));
        String next = finished.path("nextStageId").asString();
        JsonNode nextList = json(expect(stage.hr().get("/api/stages/" + next + "/candidates"), 200));
        assertThat(nextList.path("total").asLong()).isEqualTo(2);
    }

    @Test
    @DisplayName("지원자 카드는 문서 본문과 AI 분석 근거를 주고, 다른 기업은 전형을 볼 수 없다")
    void candidateCardAndCompanyIsolation() throws Exception {
        Stage stage = startDocumentStage(1);
        String id = stage.ids().getFirst();
        JsonNode card = json(expect(stage.hr().get(stage.path() + "/candidates/" + id), 200));
        assertThat(card.path("documents").get(0).path("text").asString()).contains("Java");

        JsonNode analysis = json(expect(stage.hr().get(stage.path() + "/candidates/" + id + "/analysis"), 200));
        assertThat(analysis.path("conditions").get(0).path("met").asBoolean()).isTrue();
        assertThat(analysis.path("highlights").size()).isPositive();

        expect(stage.hr().put(stage.path() + "/candidates/" + id + "/memo", Map.of("memo", "면접에서 확인")), 204);
        assertThat(json(expect(stage.hr().get(stage.path() + "/candidates/" + id), 200)).path("memo").asString())
                .isEqualTo("면접에서 확인");

        TestApi other = newHr();
        expect(other.get(stage.path()), 404);
        expect(other.post(stage.path() + "/decisions", Map.of("applicationIds", List.of(id), "decision", "PASS")),
                404);
    }

    @Test
    @DisplayName("AI Chat은 찾기 · 좁히기 · 편집을 서버 검증으로 실행하고, 차별 조건과 없는 자료 질문은 실행하지 않는다")
    void chatFindsNarrowsEditsAndBlocks() throws Exception {
        Stage stage = startDocumentStage(3);
        String chat = stage.path() + "/chat";

        JsonNode found = json(expect(stage.hr().post(chat, chatBody("Java 경험이 있는 지원자 찾아줘", List.of())), 200));
        assertThat(found.path("intent").asString()).isEqualTo("FIND");
        assertThat(found.path("message").asString()).contains("3명 중", "2명");
        JsonNode selection = json(expect(stage.hr().get(stage.path() + "/selection"), 200));
        assertThat(selection.path("total").asLong()).isEqualTo(2);
        assertThat(selection.path("items").get(0).path("aiSelected").asBoolean()).isTrue();

        JsonNode removed = json(expect(stage.hr().post(chat,
                chatBody("이 지원자 빼줘", List.of(stage.ids().get(1)))), 200));
        assertThat(removed.path("intent").asString()).isEqualTo("EDIT");
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(1);

        JsonNode blocked = json(expect(stage.hr().post(chat, chatBody("30살 이하 남자 지원자 찾아줘", List.of())), 200));
        assertThat(blocked.path("intent").asString()).isEqualTo("BLOCKED");
        JsonNode unavailable = json(expect(stage.hr().post(chat,
                chatBody("평가 결과는 좋은데 지원서와 차이가 큰 사람 있어?", List.of())), 200));
        assertThat(unavailable.path("message").asString()).contains("아직 평가 결과가 없어요");

        JsonNode analysis = json(expect(stage.hr().post(chat,
                chatBody("강점과 확인할 점은?", List.of(stage.ids().getFirst()))), 200));
        assertThat(analysis.path("intent").asString()).isEqualTo("ANSWER");
        assertThat(analysis.path("selectionChanged").asBoolean()).isFalse();
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(1);
    }

    private static Map<String, Object> chatBody(String message, List<String> mentions) {
        return Map.of("message", message, "mentionIds", mentions, "checkedIds", List.of());
    }

    private Stage startDocumentStage(int applicants) throws Exception {
        TestApi hr = newHr();
        ApplyTests.Posting posting = ApplyTests.publish(hr, false);
        for (int i = 1; i <= applicants; i++) {
            Map<String, Object> form = ApplyTests.form("applicant" + i + "@example.com", false);
            form.put("name", "지원자" + i);
            expect(anonymous().multipart(posting.applyPath(), form), 201);
        }
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        awaitAnalyzed(hr.companyId(), recruitmentId, applicants);
        List<String> ids = new ArrayList<>();
        // 점수를 고정해 지원자1이 가장 높고 마지막 지원자는 기준 미달이 되게 한다
        for (var applicant : applications.applicants(hr.companyId(), recruitmentId)) {
            int order = Integer.parseInt(applicant.name().replace("지원자", ""));
            boolean last = order == applicants && applicants > 1;
            applications.recordAnalysis(applicant.applicationId(),
                    new ApplicationAnalysis(order, "OO카드", 100 - order * 10 - (last ? 40 : 0), !last));
        }
        applications.applicants(hr.companyId(), recruitmentId).stream()
                .sorted(java.util.Comparator.comparing(applicant -> applicant.name()))
                .forEach(applicant -> ids.add(applicant.applicationId().toString()));
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
