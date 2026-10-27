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
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.QualificationStatus;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
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
    private TestMailConfiguration.RecordingMailClient mail;

    @Test
    @DisplayName("마감하면 지원자 전원이 첫 전형 대상이 되고, 서류 점수 순으로 서며 상위만 AI 추천이다")
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
    @DisplayName("서류 전형은 자격요건 점수 순(같으면 총점 순)으로 전원을 세우고, 보류는 확인 필요를 0점으로 계산한 점수로 선다")
    void documentStageSortsByQualificationThenTotal() throws Exception {
        Stage stage = startDocumentStage(6);
        record(stage, Map.of(
                1, scored(50, 80, true),
                2, scored(50, 90, true),
                3, scored(37.5, 95, true),
                // 확인 필요가 남아 점수를 보류했다. 확인 필요를 0점으로 계산하면 자격요건 25, 총점 60
                4, held(25, 60),
                5, scored(25, 70, false),
                6, scored(45, 50, true)));

        JsonNode items = json(expect(stage.hr().get(stage.path() + "/candidates?size=50"), 200)).path("items");

        // 자격요건 미달(지원자5)과 보류(지원자4)도 따로 묶지 않고 같은 줄에서 점수로 선다
        assertThat(names(items)).containsExactly("지원자2", "지원자1", "지원자6", "지원자3", "지원자5", "지원자4");
        JsonNode held = items.get(5);
        assertThat(held.path("held").asBoolean()).isTrue();
        assertThat(held.path("documentScore").isNull()).isTrue();
        assertThat(held.path("documentScoreLow").decimalValue()).isEqualByComparingTo("60");

        JsonNode byTotal = json(expect(stage.hr().get(stage.path() + "/candidates?size=50&sort=TOTAL"), 200))
                .path("items");
        assertThat(names(byTotal)).containsExactly("지원자3", "지원자2", "지원자1", "지원자5", "지원자4", "지원자6");
    }

    @Test
    @DisplayName("AI 추천은 선발 인원 10배수까지이고, 끝 순위와 점수가 같은 지원자는 모두 추천한다")
    void recommendationKeepsTiesAtTheLine() throws Exception {
        Stage stage = startDocumentStage(13);
        Map<Integer, ApplicationAnalysis> analyses = new HashMap<>();
        for (int order = 1; order <= 13; order++) {
            // 9등까지는 점수가 모두 다르고 10 ~ 12등은 공동이다. 13등은 추천 밖이다
            analyses.put(order, scored(50, order <= 9 ? 100 - order : order <= 12 ? 80 : 70, true));
        }
        record(stage, analyses);

        JsonNode items = json(expect(stage.hr().get(stage.path() + "/candidates?size=50"), 200)).path("items");

        // 선발 인원 1명(더미) × 10 = 10명이지만 공동 10등 3명을 모두 넣어 12명이다
        List<Boolean> above = new ArrayList<>();
        items.forEach(item -> above.add(item.path("aboveLine").asBoolean()));
        assertThat(above.subList(0, 12)).containsOnly(true);
        assertThat(above.get(12)).isFalse();
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
        String chat = stage.path() + "/chat";

        JsonNode found = done(expect(stage.hr().post(chat, chatBody("Java 경험이 있는 지원자 찾아줘", List.of())), 200));
        assertThat(found.path("intent").asString()).isEqualTo("FIND");
        assertThat(found.path("message").asString()).contains("3명 중", "2명");
        JsonNode selection = json(expect(stage.hr().get(stage.path() + "/selection"), 200));
        assertThat(selection.path("total").asLong()).isEqualTo(2);
        assertThat(selection.path("items").get(0).path("aiSelected").asBoolean()).isTrue();

        JsonNode removed = done(expect(stage.hr().post(chat,
                chatBody("이 지원자 빼줘", List.of(stage.ids().get(1)))), 200));
        assertThat(removed.path("intent").asString()).isEqualTo("EDIT");
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(1);

        JsonNode blocked = done(expect(stage.hr().post(chat, chatBody("30살 이하 남자 지원자 찾아줘", List.of())), 200));
        assertThat(blocked.path("intent").asString()).isEqualTo("BLOCKED");
        JsonNode unavailable = done(expect(stage.hr().post(chat,
                chatBody("평가 결과는 좋은데 지원서와 차이가 큰 사람 있어?", List.of())), 200));
        assertThat(unavailable.path("message").asString()).contains("아직 평가 결과가 없어요");

        JsonNode analysis = done(expect(stage.hr().post(chat,
                chatBody("강점과 확인할 점은?", List.of(stage.ids().getFirst()))), 200));
        assertThat(analysis.path("intent").asString()).isEqualTo("ANSWER");
        assertThat(analysis.path("selectionChanged").asBoolean()).isFalse();
        assertThat(json(expect(stage.hr().get(stage.path() + "/selection"), 200)).path("total").asLong()).isEqualTo(1);
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
        expect(hr.post(stage.path() + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
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
        expect(hr.post(stage.path() + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
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
        expect(hr.post(next + "/selection/add", Map.of("applicationIds", stage.ids().subList(0, 1))), 204);
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
        JsonNode report = awaitReport(hr, recruitment);
        assertThat(report.path("content").path("stages").size()).isEqualTo(2);
        assertThat(report.path("content").path("finalists").get(0).path("name").asString()).isEqualTo("지원자1");
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
        assertThat(prepared.questions().getFirst().text()).isEqualTo("1분 자기소개 부탁드립니다.");
        JsonNode pending = json(expect(hr.get("/api/stages/" + nextId), 200));
        assertThat(pending.path("status").asString()).isEqualTo("PENDING");
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
        JsonNode beforeChat = json(expect(hr.get(card), 200));
        JsonNode addition = done(expect(hr.post(first + "/chat",
                Map.of("message", "프로젝트 기반 질문 1개 추가해줘", "mentionIds", List.of(id),
                        "checkedIds", List.of())), 200));
        assertThat(addition.path("selectionChanged").asBoolean()).isFalse();
        assertThat(addition.path("agents").toString()).contains("Interview Agent");
        assertThat(json(expect(hr.get(card), 200)).path("questions").size())
                .isEqualTo(beforeChat.path("questions").size() + 1);
        expect(hr.post(card + "/generate", Map.of()), 404);
        expect(hr.post(first + "/chat",
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

        JsonNode chat = done(expect(hr.post(first + "/chat",
                Map.of("message", "지원자별 맞춤 질문 만들어줘", "mentionIds", List.of(), "checkedIds", List.of())), 200));
        assertThat(chat.path("agents").get(0).asString()).isEqualTo("Interview Agent");
        assertThat(chat.path("items").get(0).path("label").asString()).isEqualTo("지원자1");

        String last = passAndFinish(hr, first, id);
        JsonNode next = json(expect(hr.get(last + "/candidates/" + id + "/interview"), 200));
        assertThat(next.path("questions").get(0).path("text").asString()).isEqualTo("1분 자기소개 부탁드립니다.");
        assertThat(next.path("previous").get(0).path("stageName").asString()).isEqualTo("1차 면접");
        assertThat(next.path("previous").get(0).path("questions").size()).isPositive();
        expect(hr.post(last + "/chat", Map.of("message", "확인 안 된 부분 중심으로 질문 만들어줘",
                "mentionIds", List.of(id), "checkedIds", List.of())), 200);
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

    private static JsonNode awaitReport(TestApi hr, String recruitmentId) throws Exception {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            var response = hr.get("/api/recruitments/" + recruitmentId + "/report");
            if (response.statusCode() == 200) {
                return json(response);
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Report was not generated.");
    }

    /** 제출 서류를 비운 입사 안내. 기타 안내는 빈 줄을 섞어 쓴다. */
    private static Map<String, Object> onboarding(String startDate) {
        return Map.of("startDate", startDate, "place", "서울 중구 본사 5층", "documents", "", "preparation", "신분증",
                "note", "\n 11월 25일까지 서류를 보내 주세요 \n");
    }

    private static Map<String, Object> chatBody(String message, List<String> mentions) {
        return Map.of("message", message, "mentionIds", mentions, "checkedIds", List.of());
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
        // 점수를 고정해 지원자1이 가장 높고 마지막 지원자는 자격요건 미달로 선 아래가 되게 한다
        for (var applicant : applications.applicants(hr.companyId(), recruitmentId)) {
            int order = Integer.parseInt(applicant.name().replace("지원자", ""));
            boolean last = order == applicants && applicants > 1;
            applications.recordAnalysis(applicant.applicationId(), ApplicationAnalysis.of(order, "OO카드",
                    BigDecimal.valueOf(100 - order * 10 - (last ? 40 : 0)), !last, false, last ? List.of("신입") : List.of()));
        }
        applications.applicants(hr.companyId(), recruitmentId).stream()
                .sorted(java.util.Comparator.comparing(applicant -> applicant.name()))
                .forEach(applicant -> ids.add(applicant.applicationId().toString()));
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        return new Stage(hr, closed.path("stages").get(0).path("id").asString(), ids);
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

    /** 확정 점수. 확인 필요가 없어 0점으로 계산한 점수도 같다. */
    private static ApplicationAnalysis scored(double qualification, double total, boolean passed) {
        BigDecimal score = BigDecimal.valueOf(total);
        BigDecimal qualificationScore = BigDecimal.valueOf(qualification);
        return new ApplicationAnalysis(3, "OO카드", null,
                passed ? QualificationStatus.PASSED : QualificationStatus.FAILED, null, qualificationScore, 50,
                score.subtract(qualificationScore), 50, score, score, qualificationScore, passed, false, List.of());
    }

    /** 확인 필요가 남아 점수를 보류한 결과. 확인 필요를 0점으로 계산한 점수만 있다. */
    private static ApplicationAnalysis held(double qualificationLow, double low) {
        return new ApplicationAnalysis(3, "OO카드", null, QualificationStatus.UNDETERMINED, null, null, 50, null, 50,
                null, BigDecimal.valueOf(low), BigDecimal.valueOf(qualificationLow), false, true,
                List.of("경력 확인 필요"));
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
