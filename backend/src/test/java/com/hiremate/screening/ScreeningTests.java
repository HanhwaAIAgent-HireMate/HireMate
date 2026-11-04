package com.hiremate.screening;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.TestMailConfiguration;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.CriterionMark;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import java.math.BigDecimal;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class ScreeningTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Autowired
    private InterviewService interviews;

    @Autowired
    private ScreeningService screening;

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Test
    @DisplayName("마감하면 지원자 전원이 첫 전형 대상이 되고, 필수 조건을 채운 지원자만 선 위에 충족 개수 순으로 선다")
    void documentStageListsApplicantsByMetCount() throws Exception {
        Stage stage = startDocumentStage(4);
        JsonNode list = json(expect(stage.hr().get(stage.path() + "/candidates"), 200));
        assertThat(list.path("total").asLong()).isEqualTo(4);
        assertThat(names(list.path("items"))).containsExactly("지원자1", "지원자2", "지원자3", "지원자4");
        JsonNode first = list.path("items").get(0);
        assertThat(first.path("aboveLine").asBoolean()).isTrue();
        assertThat(first.path("metCount").asInt()).isEqualTo(8);
        assertThat(first.path("criterionTotal").asInt()).isEqualTo(10);
        JsonNode last = list.path("items").get(3);
        assertThat(last.path("aboveLine").asBoolean()).isFalse();
        assertThat(last.path("missingRequired")).extracting(JsonNode::asString).containsExactly("Q-01");

        JsonNode overview = json(expect(stage.hr().get(stage.path()), 200));
        assertThat(overview.path("type").asString()).isEqualTo("DOCUMENT");
        assertThat(overview.path("counts").path("pending").asLong()).isEqualTo(4);
        assertThat(overview.path("steps").get(0).path("targetCount").asLong()).isEqualTo(4);
    }

    @Test
    @DisplayName("필수 자격요건을 못 채우면 개수가 많아도 맨 아래이고, 충족 개수에 상인 인재상 개수를 더해 세우며 같으면 이름 순이다")
    void documentStageSortsByCountThenName() throws Exception {
        Stage stage = startDocumentStage(5);
        expect(stage.hr().put("/api/companies/me/profile", Map.of("intro", "", "culture", "",
                "talents", List.of(Map.of("title", "협업", "description", ""), Map.of("title", "끈기", "description", "")),
                "benefits", List.of())), 200);
        record(stage, Map.of(
                1, marked(3, true),
                2, marked(5, true),
                3, marked(4, true),
                // 충족 개수는 가장 많지만 필수 조건(Q-01)을 확인하지 못했다
                4, marked(9, false),
                5, marked(4, true)));
        Map<String, String> ids = idsByName(stage);
        applications.recordTalents(UUID.fromString(ids.get("지원자3")), List.of("협업", "끈기"), List.of());
        // 지금 인재상에 없는 제목은 세지 않는다
        applications.recordTalents(UUID.fromString(ids.get("지원자1")), List.of("예전 인재상"), List.of());

        JsonNode talent = json(expect(stage.hr().get(stage.path() + "/candidates?size=50"), 200)).path("items");
        assertThat(names(talent)).containsExactly("지원자3", "지원자2", "지원자5", "지원자1", "지원자4");
        assertThat(talent.get(4).path("aboveLine").asBoolean()).isFalse();
        assertThat(talent.get(0).path("talentCount").asInt()).isEqualTo(2);
        assertThat(talent.get(0).path("talentTotal").asInt()).isEqualTo(2);
        assertThat(talent.get(3).path("talentCount").asInt()).isZero();
    }

    @Test
    @DisplayName("거르기는 결정 상태가 하나라도 맞으면, 평가 항목과 인재상은 모두 O 또는 중 이상이어야 남긴다")
    void filtersByDecisionCriteriaAndTalents() throws Exception {
        Stage stage = startDocumentStage(3);
        expect(stage.hr().put("/api/companies/me/profile", Map.of("intro", "", "culture", "",
                "talents", List.of(Map.of("title", "협업", "description", ""), Map.of("title", "끈기", "description", "")),
                "benefits", List.of())), 200);
        // 앞에서부터 Q-01 … Q-05, P-01 … 순서로 채운다. Q-04는 지원자1 · 2, P-03은 지원자1만 채웠다
        record(stage, Map.of(1, marked(8, true), 2, marked(6, true), 3, partly(marked(3, true), "P-03")));
        Map<String, String> ids = idsByName(stage);
        applications.recordTalents(UUID.fromString(ids.get("지원자2")), List.of("끈기"), List.of());
        applications.recordTalents(UUID.fromString(ids.get("지원자3")), List.of(), List.of("끈기"));
        expect(stage.hr().post(stage.tabPath() + "/selection/add",
                Map.of("applicationIds", List.of(ids.get("지원자1")))), 204);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(ids.get("지원자1")), "decision", "PASS")), 204);

        assertThat(filtered(stage, "decision=PENDING&decision=FAIL")).containsExactly("지원자2", "지원자3");
        assertThat(filtered(stage, "criterion=Q-04")).containsExactly("지원자1", "지원자2");
        // 지원자3은 P-03을 부분 충족(중)했다
        assertThat(filtered(stage, "criterion=P-03")).containsExactly("지원자1", "지원자3");
        assertThat(filtered(stage, "criterion=Q-04&criterion=P-03")).containsExactly("지원자1");
        // 지원자2는 끈기가 상, 지원자3은 중이다
        assertThat(filtered(stage, "talent=T-2")).containsExactly("지원자2", "지원자3");
        assertThat(filtered(stage, "talent=T-1")).isEmpty();
        assertThat(filtered(stage, "talent=T-9")).isEmpty();
        assertThat(filtered(stage, "decision=PENDING&criterion=Q-04")).containsExactly("지원자2");
        assertThat(json(expect(stage.hr().get(stage.path() + "/candidates?criterion=Q-04"), 200))
                .path("total").asLong()).isEqualTo(2);
    }

    @Test
    @DisplayName("기준 미달 지원자는 ↑로 올린 뒤에만 넣고, 빼기는 결정이 아니다")
    void belowLineNeedsPromotionBeforeAdding() throws Exception {
        Stage stage = startDocumentStage(3);
        String below = stage.ids().get(2);
        expect(stage.hr().post(stage.tabPath() + "/selection/add", Map.of("applicationIds", List.of(below))), 409);
        expect(stage.hr().post(stage.path() + "/candidates/" + below + "/promote", null), 204);
        expect(stage.hr().post(stage.tabPath() + "/selection/add", Map.of("applicationIds", List.of(below))), 204);

        JsonNode selection = json(expect(stage.hr().get(stage.tabPath() + "/selection"), 200));
        assertThat(selection.path("total").asLong()).isEqualTo(1);
        assertThat(selection.path("items").get(0).path("aiSelected").asBoolean()).isFalse();

        expect(stage.hr().post(stage.tabPath() + "/selection/remove", Map.of("applicationIds", List.of(below))), 204);
        JsonNode row = json(expect(stage.hr().get(stage.path() + "/candidates?query=지원자3"), 200)).path("items").get(0);
        assertThat(row.path("decision").asString()).isEqualTo("PENDING");
        assertThat(row.path("selected").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("결정하면 선택 지원자에서 빠지고, 되돌리면 돌아오며, 확정하면 미결정은 불합격이 된다")
    void decisionsAndConfirmation() throws Exception {
        Stage stage = startDocumentStage(3);
        List<String> top = stage.ids().subList(0, 2);
        expect(stage.hr().post(stage.tabPath() + "/selection/add", Map.of("applicationIds", top)), 204);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(top.get(0)), "decision", "PASS")), 204);
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isEqualTo(1);

        expect(stage.hr().post(stage.path() + "/decisions/revert",
                Map.of("applicationIds", List.of(top.get(0)), "tabId", stage.tabId())), 204);
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isEqualTo(2);

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

        expect(stage.hr().post(stage.path() + "/finish", null), 409);
        expect(stage.hr().post(stage.path() + "/notices/prepare", null), 200);
        expect(stage.hr().post(stage.path() + "/notices/PASS/send", null), 200);
        expect(stage.hr().post(stage.path() + "/notices/FAIL/send", null), 200);
        JsonNode finished = json(expect(stage.hr().post(stage.path() + "/finish", null), 200));
        String next = finished.path("nextStageId").asString();
        JsonNode nextList = json(expect(stage.hr().get("/api/stages/" + next + "/candidates"), 200));
        assertThat(nextList.path("total").asLong()).isEqualTo(2);
    }

    @Test
    @DisplayName("탭은 모두 새 탭으로 시작하고, 만들고 이름을 바꾸고 지울 수 있지만 마지막 탭은 지울 수 없다")
    void tabsCanBeCreatedRenamedAndDeleted() throws Exception {
        Stage stage = startDocumentStage(1);
        JsonNode tabs = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(tabs.size()).isEqualTo(1);
        assertThat(tabs.get(0).path("name").asString()).isEqualTo("새 탭");
        assertThat(tabs.get(0).path("selectedCount").asLong()).isZero();

        String second = newTab(stage);
        JsonNode created = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(created.size()).isEqualTo(2);
        assertThat(created.get(0).path("id").asString()).isEqualTo(stage.tabId());
        assertThat(created.get(1).path("id").asString()).isEqualTo(second);
        assertThat(created.get(0).path("name").asString()).isEqualTo("새 탭");
        assertThat(created.get(1).path("name").asString()).isEqualTo("새 탭");
        JsonNode renamed = json(expect(stage.hr().patch(stage.tabPath(second), Map.of("name", "금융 경험")), 200));
        assertThat(renamed.path("name").asString()).isEqualTo("금융 경험");
        expect(stage.hr().patch(stage.tabPath(second), Map.of("name", " ")), 400);
        expect(stage.hr().patch(stage.tabPath(second), Map.of("name", "가".repeat(31))), 400);

        expect(stage.hr().delete(stage.tabPath()), 204);
        JsonNode left = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(left.size()).isEqualTo(1);
        assertThat(left.get(0).path("name").asString()).isEqualTo("금융 경험");
        assertCode(expect(stage.hr().delete(stage.tabPath(second)), 409), "LAST_TAB");
        JsonNode third = json(expect(stage.hr().post(stage.path() + "/tabs", null), 201));
        assertThat(third.path("name").asString()).isEqualTo("새 탭");
        JsonNode ordered = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(ordered.size()).isEqualTo(2);
        assertThat(ordered.get(0).path("id").asString()).isEqualTo(second);
        assertThat(ordered.get(1).path("id").asString()).isEqualTo(third.path("id").asString());
    }

    @Test
    @DisplayName("탭은 전형마다 20개까지 만든다")
    void tabsAreLimitedPerStage() throws Exception {
        Stage stage = startDocumentStage(1);
        for (int i = 2; i <= 20; i++) {
            newTab(stage);
        }
        assertCode(expect(stage.hr().post(stage.path() + "/tabs", null), 409), "TAB_LIMIT");
    }

    @Test
    @DisplayName("선택 지원자는 탭마다 따로이고, 전체 지원자 리스트는 고른 탭의 선택 표시를 보여 준다")
    void selectionIsPerTab() throws Exception {
        Stage stage = startDocumentStage(3);
        String other = newTab(stage);
        expect(stage.hr().post(stage.tabPath() + "/selection/add",
                Map.of("applicationIds", List.of(stage.ids().getFirst()))), 204);

        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isEqualTo(1);
        assertThat(selection(stage, other).path("total").asLong()).isZero();
        String row = stage.path() + "/candidates?query=지원자1&tabId=";
        assertThat(json(expect(stage.hr().get(row + stage.tabId()), 200)).path("items").get(0).path("selected")
                .asBoolean()).isTrue();
        assertThat(json(expect(stage.hr().get(row + other), 200)).path("items").get(0).path("selected")
                .asBoolean()).isFalse();
        JsonNode tabs = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(tabs.get(0).path("selectedCount").asLong()).isEqualTo(1);
        assertThat(tabs.get(1).path("selectedCount").asLong()).isZero();
    }

    @Test
    @DisplayName("결정하면 모든 탭의 선택 지원자에서 숨고, 되돌리면 원래 탭에 AI 표시 그대로 돌아오며 없던 탭에는 누른 탭으로 들어온다")
    void decisionsHideFromTabsAndRevertReturnsThem() throws Exception {
        Stage stage = startDocumentStage(3);
        String other = newTab(stage);
        List<String> top = stage.ids().subList(0, 2);
        expect(stage.hr().post(stage.tabPath() + "/selection/add", Map.of("applicationIds", top.subList(0, 1))), 204);
        screening.addByAi(stage.hr().companyId(), UUID.fromString(stage.stageId()), UUID.fromString(other),
                List.of(UUID.fromString(top.getFirst())));
        expect(stage.hr().post(stage.path() + "/decisions", Map.of("applicationIds", top, "decision", "PASS")), 204);
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isZero();
        assertThat(selection(stage, other).path("total").asLong()).isZero();

        expect(stage.hr().post(stage.path() + "/decisions/revert", Map.of("applicationIds", top, "tabId", other)), 204);
        JsonNode mine = selection(stage, stage.tabId()).path("items");
        assertThat(names(mine)).containsExactly("지원자1");
        assertThat(mine.get(0).path("aiSelected").asBoolean()).isFalse();
        JsonNode theirs = selection(stage, other).path("items");
        assertThat(names(theirs)).containsExactly("지원자1", "지원자2");
        assertThat(theirs.get(0).path("aiSelected").asBoolean()).isTrue();
        assertThat(theirs.get(1).path("aiSelected").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("비우기는 결정하지 않은 지원자에만 적용하고, 결정한 지원자는 결정을 되돌리면 제자리로 돌아온다")
    void selectionEditsSkipDecidedApplicants() throws Exception {
        Stage stage = startDocumentStage(3);
        List<String> top = stage.ids().subList(0, 2);
        expect(stage.hr().post(stage.tabPath() + "/selection/add", Map.of("applicationIds", top)), 204);
        expect(stage.hr().post(stage.path() + "/decisions",
                Map.of("applicationIds", top.subList(0, 1), "decision", "PASS")), 204);
        expect(stage.hr().post(stage.tabPath() + "/selection/clear", null), 204);
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isZero();

        expect(stage.hr().post(stage.path() + "/decisions/revert",
                Map.of("applicationIds", top.subList(0, 1), "tabId", stage.tabId())), 204);
        assertThat(names(selection(stage, stage.tabId()).path("items"))).containsExactly("지원자1");
    }

    @Test
    @DisplayName("결과를 확정하면 탭은 남고 선택 지원자만 비며, 끝난 전형은 탭을 만들거나 지울 수 없고 이름만 바꾼다")
    void confirmationKeepsTabsAndClearsSelections() throws Exception {
        Stage stage = startDocumentStage(2);
        String other = newTab(stage);
        expect(stage.hr().post(stage.tabPath() + "/selection/add",
                Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
        expect(stage.hr().post(stage.path() + "/confirm", null), 200);

        JsonNode tabs = json(expect(stage.hr().get(stage.path() + "/tabs"), 200));
        assertThat(tabs.size()).isEqualTo(2);
        assertThat(tabs.get(0).path("selectedCount").asLong()).isZero();
        assertCode(expect(stage.hr().post(stage.path() + "/tabs", null), 409), "STAGE_NOT_ACTIVE");
        assertCode(expect(stage.hr().delete(stage.tabPath(other)), 409), "STAGE_NOT_ACTIVE");
        expect(stage.hr().patch(stage.tabPath(other), Map.of("name", "확정 뒤 정리")), 200);
    }

    @Test
    @DisplayName("다른 기업은 탭을 볼 수 없고, 다른 전형의 탭은 찾을 수 없다")
    void tabsAreScopedToStageAndCompany() throws Exception {
        Stage stage = startDocumentStage(1);
        Stage another = startDocumentStage(1);
        expect(newHr().get(stage.path() + "/tabs"), 404);
        assertCode(expect(stage.hr().get(stage.tabPath(another.tabId()) + "/selection"), 404), "TAB_NOT_FOUND");
        assertCode(expect(stage.hr().patch(stage.tabPath(another.tabId()), Map.of("name", "x")), 404),
                "TAB_NOT_FOUND");
    }

    @Test
    @DisplayName("표 보기의 열은 자격요건 · 우대사항 · 인재상 순서이고, 인재상 문장은 짧은 키워드로 쓴다")
    void tableFeaturesAndTalents() throws Exception {
        Stage stage = startDocumentStage(1);
        String id = stage.ids().getFirst();
        expect(stage.hr().put("/api/companies/me/profile", Map.of("intro", "", "culture", "",
                "talents", List.of(Map.of("title", "인성을 중요시한다", "description", ""),
                        Map.of("title", "고객 신뢰", "description", "책임감")),
                "benefits", List.of())), 200);

        JsonNode features = json(expect(stage.hr().get(stage.path() + "/table"), 200)).path("features");
        List<String> groups = new ArrayList<>();
        features.forEach(feature -> groups.add(feature.path("group").asString()));
        List<String> order = List.of("QUALIFICATION", "PREFERENCE", "TALENT");
        assertThat(groups).contains("QUALIFICATION", "TALENT")
                .isSortedAccordingTo(Comparator.comparing(order::indexOf));
        JsonNode talent = features.get(features.size() - 2);
        assertThat(talent.path("id").asString()).isEqualTo("T-1");
        assertThat(talent.path("label").asString()).isEqualTo("인성");
        assertThat(talent.path("kind").asString()).isEqualTo("EXPERIENCE");
        assertThat(features.get(features.size() - 1).path("text").asString()).isEqualTo("고객 신뢰 - 책임감");

        // 개발용(stub) 판정은 모두 확인 필요다. 실제 판정은 ai 서버에서 온다
        JsonNode fit = json(expect(stage.hr().get(stage.path() + "/candidates/" + id + "/talents"), 200));
        assertThat(fit.path("items").size()).isEqualTo(2);
        assertThat(fit.path("items").get(0).path("level").asString()).isEqualTo("UNKNOWN");
        assertThat(fit.path("stub").asBoolean()).isTrue();

        TestApi other = newHr();
        expect(other.get(stage.path() + "/table"), 404);
        expect(other.get(stage.path() + "/candidates/" + id + "/talents"), 404);
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

        // 개발용(stub) 프로필 조회는 프로필이 없는 빈 결과다. 실제 항목은 ai 서버에서 온다
        JsonNode profile = json(expect(stage.hr().get(stage.path() + "/candidates/" + id + "/profile"), 200));
        assertThat(profile.path("applicationId").asString()).isEqualTo(id);
        assertThat(profile.path("status").isNull()).isTrue();
        assertThat(profile.path("items").isEmpty()).isTrue();

        expect(stage.hr().put(stage.path() + "/candidates/" + id + "/memo", Map.of("memo", "면접에서 확인")), 204);
        assertThat(json(expect(stage.hr().get(stage.path() + "/candidates/" + id), 200)).path("memo").asString())
                .isEqualTo("면접에서 확인");

        TestApi other = newHr();
        expect(other.get(stage.path()), 404);
        expect(other.get(stage.path() + "/candidates/" + id + "/profile"), 404);
        expect(other.post(stage.path() + "/decisions", Map.of("applicationIds", List.of(id), "decision", "PASS")),
                404);
    }

    @Test
    @DisplayName("AI Chat은 찾기 · 좁히기 · 편집을 서버 검증으로 실행하고, 차별 조건과 없는 자료 질문은 실행하지 않는다")
    void chatFindsNarrowsEditsAndBlocks() throws Exception {
        Stage stage = startDocumentStage(3);
        String chat = stage.tabPath() + "/chat";

        JsonNode found = done(expect(stage.hr().post(chat, chatBody("Java 경험이 있는 지원자 찾아줘", List.of())), 200));
        assertThat(found.path("intent").asString()).isEqualTo("FIND");
        assertThat(found.path("message").asString()).contains("3명 중", "2명");
        JsonNode selection = json(expect(stage.hr().get(stage.tabPath() + "/selection"), 200));
        assertThat(selection.path("total").asLong()).isEqualTo(2);
        assertThat(selection.path("items").get(0).path("aiSelected").asBoolean()).isTrue();

        JsonNode removed = done(expect(stage.hr().post(chat,
                chatBody("이 지원자 빼줘", List.of(stage.ids().get(1)))), 200));
        assertThat(removed.path("intent").asString()).isEqualTo("EDIT");
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isEqualTo(1);

        JsonNode blocked = done(expect(stage.hr().post(chat, chatBody("30살 이하 남자 지원자 찾아줘", List.of())), 200));
        assertThat(blocked.path("intent").asString()).isEqualTo("BLOCKED");
        JsonNode unavailable = done(expect(stage.hr().post(chat,
                chatBody("평가 결과는 좋은데 지원서와 차이가 큰 사람 있어?", List.of())), 200));
        assertThat(unavailable.path("message").asString()).contains("아직 평가 결과가 없어요");

        JsonNode analysis = done(expect(stage.hr().post(chat,
                chatBody("강점과 확인할 점은?", List.of(stage.ids().getFirst()))), 200));
        assertThat(analysis.path("intent").asString()).isEqualTo("ANSWER");
        assertThat(analysis.path("selectionChanged").asBoolean()).isFalse();
        assertThat(selection(stage, stage.tabId()).path("total").asLong()).isEqualTo(1);
    }

    @Test
    @DisplayName("전형 종료 화면은 AI를 기다리지 않고 양식 초안을 받고, 안내 초안 화면이 그룹 하나씩 AI 초안을 쓴다")
    void noticeDraftsAreWrittenPerGroup() throws Exception {
        Stage stage = startDocumentStage(2);
        TestApi hr = stage.hr();
        expect(hr.post(stage.tabPath() + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);

        JsonNode listed = json(expect(hr.get(stage.path() + "/notices"), 200));
        assertThat(listed.get(0).path("group").asString()).isEqualTo("PASS");
        assertThat(listed.get(0).path("content").asString()).isEmpty();
        assertThat(listed.get(1).path("content").asString()).isEmpty();

        JsonNode prepared = json(expect(hr.post(stage.path() + "/notices/PASS/prepare", null), 200));
        String written = prepared.get(0).path("content").asString();
        assertThat(written).isNotBlank();
        assertThat(prepared.get(1).path("content").asString()).isEmpty();
        JsonNode again = json(expect(hr.post(stage.path() + "/notices/PASS/prepare", null), 200));
        assertThat(again.get(0).path("content").asString()).isEqualTo(written);
        expect(newHr().post(stage.path() + "/notices/PASS/prepare", null), 404);
    }

    @Test
    @DisplayName("다음 전형 안내에는 보내는 때의 다음 전형 안내가 붙고, 공고 화면은 안내를 받은 지원자 수를 알려 준다")
    void nextStageNoticeCarriesStageGuide() throws Exception {
        Stage stage = startDocumentStage(2);
        TestApi hr = stage.hr();
        String recruitment = json(expect(hr.get(stage.path()), 200)).path("recruitmentId").asString();
        String guides = "/api/recruitments/" + recruitment + "/stage-guides";
        String guidePath = "/api/stages/"
                + json(expect(hr.get(guides), 200)).get(0).path("stageId").asString() + "/guide";
        LocalDate first = LocalDate.now().plusDays(10);
        String firstText = first.format(DateTimeFormatter.ofPattern("yyyy년 M월 d일(E)", Locale.KOREAN));
        expect(hr.put(guidePath, Map.of("schedule", first.toString(), "method", "ONLINE", "place", "",
                "preparation", "신분증", "note", "11월 1일까지 참석 여부를 알려 주세요.\n\n 건물 주차는 지원되지 않습니다. ")),
                200);
        expect(hr.post(stage.tabPath() + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);

        JsonNode notices = json(expect(hr.post(stage.path() + "/notices/prepare", null), 200));
        assertThat(notices.get(0).path("guide").asString()).isEqualTo("""
                일정과 준비 사항은 아래 안내를 확인해 주시기 바랍니다.

                ■ 1차 면접 안내
                - 일정: %s
                - 진행 방식: 온라인
                - 준비 사항: 신분증

                ※ 11월 1일까지 참석 여부를 알려 주세요.
                ※ 건물 주차는 지원되지 않습니다.""".formatted(firstText));
        assertThat(notices.get(0).path("guideMissing").toString()).isEqualTo("[\"장소·접속 링크\"]");
        assertThat(notices.get(1).path("guide").asString()).isEmpty();
        assertThat(notices.get(1).path("guideMissing").size()).isZero();
        JsonNode preview = json(expect(hr.get(stage.path() + "/notices/PASS/preview"), 200));
        assertThat(preview.path("html").asString()).containsSubsequence("홍길동님", ">1차 면접 안내</td>", ">일정</td>",
                ">" + firstText + "</td>", "※ 건물 주차는 지원되지 않습니다.");

        LocalDate second = first.plusDays(1);
        String secondText = second.format(DateTimeFormatter.ofPattern("yyyy년 M월 d일(E)", Locale.KOREAN));
        expect(hr.put(guidePath, Map.of("schedule", second.toString(), "place", "", "preparation", "", "note", "")),
                200);
        expect(hr.post(stage.path() + "/notices/PASS/send", null), 200);
        assertThat(mail.sent).anySatisfy(message -> assertThat(message)
                .contains("지원자1님", "다음 전형은 1차 면접입니다.", "■ 1차 면접 안내\n- 일정: " + secondText)
                .doesNotContain("신분증"));
        assertThat(mail.html).anySatisfy(html -> assertThat(html)
                .containsSubsequence("지원자1님", ">1차 면접 안내</td>", ">" + secondText + "</td>"));
        assertThat(json(expect(hr.get(guides), 200)).get(0).path("notifiedCount").asInt()).isEqualTo(1);
    }

    @Test
    @DisplayName("안내는 확인한 초안을 변수를 채워 보내고, 마지막 전형을 종료하면 채용이 끝나고 리포트가 만들어진다")
    void noticesAndFinalReport() throws Exception {
        Stage stage = startDocumentStage(2);
        TestApi hr = stage.hr();
        expect(hr.post(stage.tabPath() + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);

        JsonNode notices = json(expect(hr.post(stage.path() + "/notices/prepare", null), 200));
        assertThat(notices.get(0).path("label").asString()).isEqualTo("다음 전형 안내");
        assertThat(notices.get(0).path("content").asString()).contains("1차 면접");
        JsonNode revised = json(expect(hr.post(stage.path() + "/notices/FAIL/ai-requests",
                Map.of("message", "말투를 더 따뜻하게 바꿔줘")), 200));
        assertThat(revised.path("content").asString()).contains("소중히");
        JsonNode fail = notices.get(1);
        expect(hr.put(stage.path() + "/notices/FAIL", Map.of("subject", fail.path("subject").asString(),
                "greeting", fail.path("greeting").asString(), "content", revised.path("content").asString(),
                "closing", fail.path("closing").asString())), 200);
        expect(hr.post(stage.path() + "/notices/PASS/send", null), 200);
        JsonNode sentFail = json(expect(hr.post(stage.path() + "/notices/FAIL/send", null), 200));
        assertThat(sentFail.path("status").asString()).isEqualTo("SENT");
        assertThat(mail.sent).anySatisfy(message -> assertThat(message).contains("지원자2님", "소중히"));
        expect(hr.put(stage.path() + "/notices/FAIL", Map.of("subject", "x", "greeting", "", "content", "x",
                "closing", "")), 409);

        String interview = json(expect(hr.post(stage.path() + "/finish", null), 200)).path("nextStageId").asString();
        String next = "/api/stages/" + interview;
        expect(hr.post(next + "/tabs/" + TestFixtures.firstTab(hr, interview) + "/selection/add",
                Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
        expect(hr.post(next + "/decisions", Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")),
                204);
        expect(hr.post(next + "/confirm", null), 200);
        JsonNode last = json(expect(hr.post(next + "/notices/prepare", null), 200));
        assertThat(last.get(0).path("label").asString()).isEqualTo("최종 합격 안내");
        assertThat(last.get(0).path("guide").asString()).isEqualTo("입사 일정과 준비 사항은 담당자가 별도로 안내드릴 예정입니다.");
        assertThat(last.get(0).path("guideMissing").size()).isEqualTo(4);
        assertThat(last.get(1).path("status").asString()).isEqualTo("EMPTY");
        expect(hr.put(stage.path() + "/notices/PASS/onboarding", onboarding("12월 1일(월) 오전 9시")), 409);
        JsonNode onboarded = json(expect(hr.put(next + "/notices/PASS/onboarding",
                onboarding("12월 1일(월) 오전 9시")), 200));
        assertThat(onboarded.path("guideMissing").toString()).isEqualTo("[\"제출 서류\"]");
        expect(hr.post(next + "/notices/PASS/send", null), 200);
        assertThat(mail.sent).anySatisfy(message -> assertThat(message).contains("""
                입사 일정과 준비 사항은 아래 안내를 확인해 주시기 바랍니다.

                ■ 입사 안내
                - 입사일: 12월 1일(월) 오전 9시
                - 출근 장소: 서울 중구 본사 5층
                - 준비 사항: 신분증

                ※ 11월 25일까지 서류를 보내 주세요""").doesNotContain("별도로 안내"));
        expect(hr.put(next + "/notices/PASS/onboarding", onboarding("12월 2일")), 409);
        assertThat(json(expect(hr.post(next + "/finish", null), 200)).path("nextStageId").isNull()).isTrue();

        String recruitment = json(expect(hr.get(stage.path()), 200)).path("recruitmentId").asString();
        JsonNode finals = awaitFinalReports(hr, recruitment);
        assertThat(finals.get(0).path("stageId").asString()).isEqualTo(interview);
        JsonNode agentReport = json(expect(hr.get(next + "/reports/" + finals.get(0).path("id").asString()), 200));
        JsonNode bundle = agentReport.path("bundle");
        assertThat(bundle.path("kind").asString()).isEqualTo("FINAL");
        assertThat(bundle.path("stages")).hasSize(2);
        assertThat(bundle.path("applicants")).hasSize(2);
        assertThat(bundle.path("metrics").findValuesAsString("id")).contains("m-applicants", "m-finalists",
                "m-document-pass", "m-interview-pass");
        assertThat(bundle.toString()).doesNotContain("지원자1");
        String reopened = json(expect(hr.post("/api/recruitments/" + recruitment + "/reports/final", null), 202))
                .path("id").asString();
        assertThat(reopened).isEqualTo(finals.get(0).path("id").asString());
    }

    @Test
    @DisplayName("전형 결과 리포트는 결과를 확정하고 안내를 모두 보낸 뒤에 열고, 이미 있으면 같은 리포트를 연다")
    void stageReportOpensAfterConfirm() throws Exception {
        Stage stage = startDocumentStage(2);
        TestApi hr = stage.hr();
        expect(hr.post(stage.path() + "/reports/stage", null), 409);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", stage.ids().subList(0, 1), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);

        // 확정 때 이벤트로 만든 리포트가 생길 때까지 기다린 뒤 연다
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        JsonNode list = json(expect(hr.get(stage.path() + "/reports"), 200));
        while (list.isEmpty() && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
            list = json(expect(hr.get(stage.path() + "/reports"), 200));
        }
        String made = list.get(0).path("id").asString();
        expect(hr.post(stage.path() + "/reports/stage", null), 409);
        expect(hr.get(stage.path() + "/reports/" + made), 409);

        // 합격 · 불합격 안내를 모두 보내면 열린다
        expect(hr.post(stage.path() + "/notices/prepare", null), 200);
        expect(hr.post(stage.path() + "/notices/PASS/send", null), 200);
        expect(hr.post(stage.path() + "/notices/FAIL/send", null), 200);
        String opened = json(expect(hr.post(stage.path() + "/reports/stage", null), 202)).path("reportId").asString();
        assertThat(opened).isEqualTo(made);
        expect(hr.get(stage.path() + "/reports/" + made), 200);
        String recruitment = json(expect(hr.get(stage.path()), 200)).path("recruitmentId").asString();
        expect(hr.post("/api/recruitments/" + recruitment + "/reports/final", null), 409);
    }

    @Test
    @DisplayName("평가 전형은 결과표를 이메일로 맞춰 점수를 등록하고, 점수 높은 순으로 보여 준다")
    void assessmentResultsAreImported() throws Exception {
        Stage stage = startDocumentStage(2, "전형은 서류, 직무역량 평가 순으로 해줘");
        TestApi hr = stage.hr();
        // 결정은 선택 지원자에 넣지 않아도 체크만으로 할 수 있다
        expect(hr.post(stage.path() + "/decisions", Map.of("applicationIds", stage.ids(), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);
        expect(hr.post(stage.path() + "/notices/prepare", null), 200);
        expect(hr.post(stage.path() + "/notices/PASS/send", null), 200);
        String assessment = "/api/stages/" + json(expect(hr.post(stage.path() + "/finish", null), 200))
                .path("nextStageId").asString();

        JsonNode preview = json(expect(hr.multipart(assessment + "/assessment/preview", Map.of("file",
                new TestApi.FilePart("result.csv", "text/csv",
                        "이메일,총점\napplicant1@example.com,72\napplicant2@example.com,91\nghost@example.com,50\n"
                                .getBytes(java.nio.charset.StandardCharsets.UTF_8)))), 200));
        assertThat(preview.path("columns").get(1).asString()).isEqualTo("총점");
        List<Map<String, Object>> entries = List.of(
                Map.of("identifier", "applicant1@example.com", "total", 72, "areas", Map.of("의사소통능력", 70)),
                Map.of("identifier", "applicant2@example.com", "total", 91, "areas", Map.of()),
                Map.of("identifier", "ghost@example.com", "total", 50, "areas", Map.of()));
        JsonNode dryRun = json(expect(hr.post(assessment + "/assessment/import?dryRun=true",
                Map.of("identifierType", "EMAIL", "entries", entries)), 200));
        assertThat(dryRun.path("matched").asInt()).isEqualTo(2);
        assertThat(dryRun.path("unmatched").get(0).asString()).isEqualTo("ghost@example.com");
        expect(hr.post(assessment + "/assessment/import", Map.of("identifierType", "EMAIL", "entries", entries)), 200);

        JsonNode list = json(expect(hr.get(assessment + "/candidates"), 200));
        assertThat(list.path("items").get(0).path("name").asString()).isEqualTo("지원자2");
        assertThat(list.path("items").get(0).path("score").asInt()).isEqualTo(91);
        JsonNode result = json(expect(hr.get(assessment + "/assessment/results/" + stage.ids().getFirst()), 200));
        assertThat(result.path("areas").path("의사소통능력").asInt()).isEqualTo(70);

        // 수동 입력과 제출 URL은 화면이 일부 칸만 보낸다. 보내지 않은 칸(빈 영역 점수, null)은 그대로 둔다
        String manual = assessment + "/assessment/results/" + stage.ids().getFirst();
        Map<String, Object> scoreOnly = new HashMap<>(Map.of("total", 75, "areas", Map.of(), "grade", "B",
                "note", "코드 구조 설명이 명확했음"));
        scoreOnly.put("url", null);
        expect(hr.put(manual, scoreOnly), 200);
        Map<String, Object> urlOnly = new HashMap<>(Map.of("total", 75, "areas", Map.of(),
                "url", "https://github.com/example/assignment"));
        urlOnly.put("grade", null);
        urlOnly.put("note", null);
        JsonNode kept = json(expect(hr.put(manual, urlOnly), 200));
        assertThat(kept.path("areas").path("의사소통능력").asInt()).isEqualTo(70);
        assertThat(kept.path("grade").asString()).isEqualTo("B");
        assertThat(kept.path("note").asString()).isEqualTo("코드 구조 설명이 명확했음");
        assertThat(kept.path("url").asString()).isEqualTo("https://github.com/example/assignment");
    }

    @Test
    @DisplayName("결과 확정 직후 합격자만 다음 면접 질문을 준비하고, 전형 시작 때 중복 생성하지 않는다 (FR-27)")
    void interviewStageStartsWithPreparedQuestions() throws Exception {
        Stage stage = startDocumentStage(3, "전형은 서류, 1차 면접 순으로 해줘");
        TestApi hr = stage.hr();
        String id = stage.ids().getFirst();
        UUID companyId = hr.companyId();
        JsonNode steps = json(expect(hr.get(stage.path()), 200)).path("steps");
        UUID nextId = UUID.fromString(steps.get(1).path("stageId").asString());
        UUID applicationId = UUID.fromString(id);
        assertThatThrownBy(() -> interviews.preparationView(companyId, nextId, applicationId))
                .isInstanceOf(ApiException.class);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(id), "decision", "PASS")), 204);
        expect(hr.post(stage.path() + "/decisions",
                Map.of("applicationIds", List.of(stage.ids().get(1)), "decision", "FAIL")), 204);
        expect(hr.post(stage.path() + "/confirm", null), 200);

        // 면접 대상자로 아직 등록하지 않아도 확정 합격자의 질문은 먼저 준비된다.
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        InterviewView prepared = interviews.preparationView(companyId, nextId, applicationId);
        while (prepared.questions().isEmpty() && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
            prepared = interviews.preparationView(companyId, nextId, applicationId);
        }
        assertThat(prepared.questions()).isNotEmpty();
        assertThat(prepared.singleInterview()).isTrue();
        assertThat(interviews.preparing(companyId, nextId, applicationId)).isFalse();
        assertThat(prepared.questions().getFirst().text()).isEqualTo("1분 자기소개 부탁드립니다.");
        JsonNode pending = json(expect(hr.get("/api/stages/" + nextId), 200));
        assertThat(pending.path("status").asString()).isEqualTo("PENDING");
        // 자기소개는 인사 기록으로 고정하고, 다른 미응답 질문은 면접 전에 담당을 바꿀 수 있다
        assertThat(prepared.questions().getFirst().interviewerRole()).isEqualTo(InterviewerRole.HR);
        String rolePath = "/api/stages/" + nextId + "/interview/questions/"
                + prepared.questions().getFirst().questionId() + "/role";
        expect(hr.put(rolePath, Map.of("interviewerRole", "PRACTICAL")), 409);
        String jobRolePath = "/api/stages/" + nextId + "/interview/questions/"
                + prepared.questions().get(1).questionId() + "/role";
        JsonNode reassigned = json(expect(hr.put(jobRolePath, Map.of("interviewerRole", "HR")), 200));
        assertThat(reassigned.path("questions").get(1).path("interviewerRole").asString()).isEqualTo("HR");
        assertThat(pending.path("counts").path("total").asLong()).isZero();
        for (String rejected : stage.ids().subList(1, 3)) {
            assertThatThrownBy(() -> interviews.addPreparedQuestions(companyId, nextId,
                    UUID.fromString(rejected), List.of("저장되면 안 되는 질문")))
                    .isInstanceOf(ApiException.class);
        }
        assertThatThrownBy(() -> interviews.preparationView(UUID.randomUUID(), nextId, applicationId))
                .isInstanceOf(ApiException.class);

        expect(hr.post(stage.path() + "/notices/prepare", null), 200);
        expect(hr.post(stage.path() + "/notices/PASS/send", null), 200);
        expect(hr.post(stage.path() + "/notices/FAIL/send", null), 200);
        expect(hr.post(stage.path() + "/finish", null), 200);
        String card = "/api/stages/" + nextId + "/candidates/" + id + "/interview";
        JsonNode opened = json(expect(hr.get(card), 200));
        assertThat(opened.path("questions").size()).isEqualTo(prepared.questions().size());
        assertThat(opened.path("questions").get(0).path("questionId").asString())
                .isEqualTo(prepared.questions().getFirst().questionId().toString());
        // 개발용(stub)은 바로 만들어서 '질문 생성 중'이 아니다
        assertThat(json(expect(hr.get(card + "/preparing"), 200)).path("preparing").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("면접 전형은 AI Chat으로 맞춤 질문을 만들고 질문별 답변을 기록하며, 다음 면접에서 이전 기록을 보여 준다")
    void interviewQuestionsAndAnswers() throws Exception {
        Stage stage = startDocumentStage(1, "전형은 서류, 1차 면접, 최종 면접 순으로 해줘");
        TestApi hr = stage.hr();
        String id = stage.ids().getFirst();
        String first = passAndFinish(hr, stage.path(), id);

        String card = first + "/candidates/" + id + "/interview";
        // 전형을 마치면 다음 면접 질문을 비동기로 미리 만든다. 다 들어온 뒤에 세야 Chat이 더한 1개만 비교된다
        JsonNode beforeChat = awaitPreparedQuestions(hr, card);
        String firstChat = TestFixtures.firstTabPath(hr, first) + "/chat";
        JsonNode addition = done(expect(hr.post(firstChat,
                Map.of("message", "프로젝트 기반 질문 1개 추가해줘", "mentionIds", List.of(id),
                        "checkedIds", List.of())), 200));
        assertThat(addition.path("selectionChanged").asBoolean()).isFalse();
        assertThat(addition.path("agents").toString()).contains("Interview Agent");
        assertThat(json(expect(hr.get(card), 200)).path("questions").size())
                .isEqualTo(beforeChat.path("questions").size() + 1);
        expect(hr.post(card + "/generate", Map.of()), 404);
        expect(hr.post(firstChat,
                Map.of("message", "맞춤 질문 만들어줘", "mentionIds", List.of(id), "checkedIds", List.of())), 200);
        JsonNode generated = json(expect(hr.get(card), 200));
        assertThat(generated.path("questions").size()).isPositive();
        assertThat(generated.path("questions").get(0).path("source").asString()).isEqualTo("AI");
        JsonNode added = json(expect(hr.post(card + "/questions", Map.of("text", "가장 어려웠던 장애 대응은?")), 200));
        String questionId = added.path("questions").get(0).path("questionId").asString();
        expect(hr.put(first + "/interview/questions/" + questionId + "/answer", Map.of("answer", "짧음")), 200);
        JsonNode scheduled = json(expect(hr.put(card + "/schedule",
                Map.of("scheduledAt", "2026-10-31T05:00:00Z", "interviewers", "면접관 2명")), 200));
        assertThat(scheduled.path("schedule").path("interviewers").asString()).isEqualTo("면접관 2명");

        JsonNode chat = done(expect(hr.post(firstChat,
                Map.of("message", "지원자별 맞춤 질문 만들어줘", "mentionIds", List.of(), "checkedIds", List.of())), 200));
        assertThat(chat.path("agents").get(0).asString()).isEqualTo("Interview Agent");
        assertThat(chat.path("items").get(0).path("label").asString()).isEqualTo("지원자1");

        String last = passAndFinish(hr, first, id);
        JsonNode next = json(expect(hr.get(last + "/candidates/" + id + "/interview"), 200));
        assertThat(next.path("questions").get(0).path("text").asString()).isEqualTo("1분 자기소개 부탁드립니다.");
        assertThat(next.path("previous").get(0).path("stageName").asString()).isEqualTo("1차 면접");
        assertThat(next.path("previous").get(0).path("questions").size()).isPositive();
        expect(hr.post(TestFixtures.firstTabPath(hr, last) + "/chat",
                Map.of("message", "확인 안 된 부분 중심으로 질문 만들어줘", "mentionIds", List.of(id),
                        "checkedIds", List.of())), 200);
        JsonNode recommended = json(expect(hr.get(last + "/candidates/" + id + "/interview"), 200));
        assertThat(recommended.path("questions").toString()).contains("충분히 확인하지 못한");
        JsonNode history = json(expect(hr.get(last + "/candidates/" + id + "/history"), 200));
        assertThat(history.size()).isEqualTo(3);
    }

    private static String passAndFinish(TestApi hr, String stagePath, String applicationId) throws Exception {
        expect(hr.post(stagePath + "/decisions", Map.of("applicationIds", List.of(applicationId), "decision", "PASS")),
                204);
        expect(hr.post(stagePath + "/confirm", null), 200);
        expect(hr.post(stagePath + "/notices/prepare", null), 200);
        expect(hr.post(stagePath + "/notices/PASS/send", null), 200);
        return "/api/stages/" + json(expect(hr.post(stagePath + "/finish", null), 200)).path("nextStageId").asString();
    }

    /** 미리 만든 면접 질문이 카드에 들어오고 준비가 끝날 때까지 기다린 카드. */
    private static JsonNode awaitPreparedQuestions(TestApi hr, String card) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        JsonNode view = json(expect(hr.get(card), 200));
        while ((view.path("questions").isEmpty()
                || json(expect(hr.get(card + "/preparing"), 200)).path("preparing").asBoolean())
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
            view = json(expect(hr.get(card), 200));
        }
        return view;
    }

    private static JsonNode awaitFinalReports(TestApi hr, String recruitmentId) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            JsonNode list = json(expect(hr.get("/api/recruitments/" + recruitmentId + "/reports"), 200));
            if (!list.isEmpty()) {
                return list;
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Final report was not requested.");
    }

    /** 제출 서류를 비운 입사 안내. 기타 안내는 빈 줄을 섞어 쓴다. */
    private static Map<String, Object> onboarding(String startDate) {
        return Map.of("startDate", startDate, "place", "서울 중구 본사 5층", "documents", "", "preparation", "신분증",
                "note", "\n 11월 25일까지 서류를 보내 주세요 \n");
    }

    private static String newTab(Stage stage) throws Exception {
        return json(expect(stage.hr().post(stage.path() + "/tabs", null), 201)).path("id").asString();
    }

    private static JsonNode selection(Stage stage, String tab) throws Exception {
        return json(expect(stage.hr().get(stage.tabPath(tab) + "/selection"), 200));
    }

    private static void assertCode(HttpResponse<String> response, String code) {
        assertThat(json(response).path("code").asString()).isEqualTo(code);
    }

    private static Map<String, Object> chatBody(String message, List<String> mentions) {
        return Map.of("message", message, "mentionIds", mentions, "checkedIds", List.of());
    }

    @Test
    @DisplayName("인재상은 설정의 인재상에 회사 소개 · 조직 문화 글에서 뽑은 요소를 더하고, 이름이 겹치면 한 번만 둔다")
    void talentsIncludeFactorsFromCompanyText() throws Exception {
        Stage stage = startDocumentStage(1);
        expect(stage.hr().put("/api/companies/me/profile", Map.of("intro", "결제 플랫폼을 만듭니다.",
                "culture", "협업을 중요시합니다. 도전하는 분을 환영합니다.",
                "talents", List.of(Map.of("title", "협업", "description", "")), "benefits", List.of())), 200);

        // 글의 요소는 저장한 뒤 AI가 따로 뽑는다
        List<String> texts = new ArrayList<>();
        Instant deadline = Instant.now().plus(Duration.ofSeconds(10));
        while (texts.size() < 2 && Instant.now().isBefore(deadline)) {
            texts.clear();
            json(expect(stage.hr().get(stage.path() + "/table"), 200)).path("features").forEach(feature -> {
                if ("TALENT".equals(feature.path("group").asString())) {
                    texts.add(feature.path("text").asString());
                }
            });
            Thread.sleep(200);
        }

        assertThat(texts).hasSize(2);
        assertThat(texts.getFirst()).isEqualTo("협업");
        assertThat(texts.get(1)).contains("도전하는 분을 환영합니다.");
    }

    @Test
    @DisplayName("블라인드 채용 서류 전형은 출신 학교를 쓴 지원자를 리스트 맨 아래에 모으고 가린 문장을 카드에 보이며, HR이 해제하면 원래 자리로 돌린다")
    void movesSchoolSuspectsDownUntilHrClears() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publishBlind(hr);
        Map<String, String> resumes = Map.of("attended@example.com", "Graduated from Hanbit University in 2020.",
                "worked@example.com", "Worked at Hanbit University office for 2 years.");
        for (Map.Entry<String, String> resume : resumes.entrySet()) {
            Map<String, Object> form = TestFixtures.form(resume.getKey(), false);
            form.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf",
                    TestFixtures.pdf(resume.getValue())));
            expect(anonymous().multipart(posting.applyPath(), form), 201);
        }
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        awaitAnalyzed(hr.companyId(), recruitmentId, 2);
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String stage = "/api/stages/" + closed.path("stages").get(0).path("id").asString();

        Map<String, List<String>> mentions = new HashMap<>();
        Map<String, String> ids = new HashMap<>();
        for (var applicant : applications.applicants(hr.companyId(), recruitmentId)) {
            JsonNode card = json(expect(hr.get(stage + "/candidates/" + applicant.applicationId()), 200));
            mentions.put(applicant.email(), card.path("schoolMentions").valueStream().map(JsonNode::asString).toList());
            ids.put(applicant.email(), applicant.applicationId().toString());
        }
        assertThat(mentions).containsEntry("attended@example.com", List.of("Graduated from ○○학교 in 2020."))
                .containsEntry("worked@example.com", List.of());

        String attended = ids.get("attended@example.com");
        JsonNode list = json(expect(hr.get(stage + "/candidates"), 200));
        assertThat(list.path("schoolSuspects")).extracting(JsonNode::asString).containsExactly(attended);
        assertThat(list.path("items").get(1).path("applicationId").asString()).isEqualTo(attended);

        // 면접관은 해제할 수 없다. HR이 해제하면 의심 목록에서 빠지고, 카드는 해제 취소를 위해 문장을 남긴다
        expect(newInterviewer(hr, "면접관").post(stage + "/candidates/" + attended + "/school-clear", null), 403);
        expect(hr.post(stage + "/candidates/" + attended + "/school-clear", null), 204);
        assertThat(json(expect(hr.get(stage + "/candidates"), 200)).path("schoolSuspects")).isEmpty();
        JsonNode cleared = json(expect(hr.get(stage + "/candidates/" + attended), 200));
        assertThat(cleared.path("schoolCleared").asBoolean()).isTrue();
        assertThat(cleared.path("schoolMentions").size()).isEqualTo(1);

        // 해제 취소하면 다시 맨 아래 의심 목록으로 간다
        expect(hr.delete(stage + "/candidates/" + attended + "/school-clear"), 204);
        assertThat(json(expect(hr.get(stage + "/candidates"), 200)).path("schoolSuspects"))
                .extracting(JsonNode::asString).containsExactly(attended);
        assertThat(json(expect(hr.get(stage + "/candidates/" + attended), 200)).path("schoolCleared").asBoolean())
                .isFalse();
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
        List<String> ids = new ArrayList<>();
        // 충족 개수를 고정해 지원자1이 가장 많고 마지막 지원자는 필수 조건(Q-01) 미달로 선 아래가 되게 한다
        for (var applicant : applications.applicants(hr.companyId(), recruitmentId)) {
            int order = Integer.parseInt(applicant.name().replace("지원자", ""));
            boolean last = order == applicants && applicants > 1;
            applications.recordAnalysis(applicant.applicationId(), marked(Math.max(2, 9 - order), !last));
        }
        applications.applicants(hr.companyId(), recruitmentId).stream()
                .sorted(java.util.Comparator.comparing(applicant -> applicant.name()))
                .forEach(applicant -> ids.add(applicant.applicationId().toString()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String stageId = closed.path("stages").get(0).path("id").asString();
        return new Stage(hr, stageId, ids, TestFixtures.firstTab(hr, stageId).toString());
    }

    /** 전형 시작 뒤 지원자N의 분석 결과를 바꾼다. 리스트는 매번 다시 줄 세운다. */
    private void record(Stage stage, Map<Integer, ApplicationAnalysis> analyses) throws Exception {
        UUID recruitmentId = UUID.fromString(json(expect(stage.hr().get(stage.path()), 200))
                .path("recruitmentId").asString());
        for (var applicant : applications.applicants(stage.hr().companyId(), recruitmentId)) {
            ApplicationAnalysis analysis = analyses.get(Integer.parseInt(applicant.name().replace("지원자", "")));
            if (analysis != null) {
                applications.recordAnalysis(applicant.applicationId(), analysis);
            }
        }
    }

    /**
     * 평가 항목 판정을 고정한 결과. 앞에서부터 met개 항목을 충족(MET)으로 두고 나머지는 미충족이다.
     * required가 false면 필수 조건 Q-01을 확인 필요로 둔다(충족 개수는 그대로).
     */
    private static ApplicationAnalysis marked(int met, boolean required) {
        Map<String, CriterionMark> marks = new LinkedHashMap<>();
        List<String> order = new ArrayList<>(List.of("Q-01", "Q-02", "Q-03", "Q-04", "Q-05", "P-01", "P-02",
                "P-03", "P-04", "P-05"));
        if (!required) {
            order.remove("Q-01");
            order.add("Q-01");
        }
        for (int index = 0; index < order.size(); index++) {
            marks.put(order.get(index), index < met ? CriterionMark.MET : CriterionMark.NOT_MET);
        }
        if (!required) {
            marks.put("Q-01", CriterionMark.UNKNOWN);
        }
        return new ApplicationAnalysis(3, "OO카드", null, required ? List.of() : List.of("경력 확인 필요"), marks);
    }

    /** 판정 하나를 부분 충족으로 바꾼다. */
    private static ApplicationAnalysis partly(ApplicationAnalysis analysis, String criterionId) {
        Map<String, CriterionMark> marks = new LinkedHashMap<>(analysis.criterionMarks());
        marks.put(criterionId, CriterionMark.PARTIAL);
        return new ApplicationAnalysis(analysis.careerYears(), analysis.lastCompany(), analysis.criteriaVersion(),
                analysis.shortfalls(), marks);
    }

    private List<String> filtered(Stage stage, String query) throws Exception {
        return names(json(expect(stage.hr().get(stage.path() + "/candidates?size=50&" + query), 200)).path("items"));
    }

    private Map<String, String> idsByName(Stage stage) throws Exception {
        UUID recruitmentId = UUID.fromString(json(expect(stage.hr().get(stage.path()), 200))
                .path("recruitmentId").asString());
        Map<String, String> ids = new HashMap<>();
        applications.applicants(stage.hr().companyId(), recruitmentId)
                .forEach(applicant -> ids.put(applicant.name(), applicant.applicationId().toString()));
        return ids;
    }

    private static List<String> names(JsonNode items) {
        List<String> names = new ArrayList<>();
        items.forEach(item -> names.add(item.path("name").asString()));
        return names;
    }

    private void awaitAnalyzed(UUID companyId, UUID recruitmentId, int count) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            if (applications.applicants(companyId, recruitmentId).stream()
                    .filter(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE).count() == count) {
                return;
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }

    record Stage(TestApi hr, String stageId, List<String> ids, String tabId) {

        String path() {
            return "/api/stages/" + stageId;
        }

        String tabPath() {
            return tabPath(tabId);
        }

        String tabPath(String tab) {
            return path() + "/tabs/" + tab;
        }
    }
}
