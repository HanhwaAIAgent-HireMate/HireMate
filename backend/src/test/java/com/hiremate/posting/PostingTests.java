package com.hiremate.posting;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.TestMailConfiguration;
import com.hiremate.posting.domain.JobPostingRepository;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class PostingTests extends IntegrationTest {

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Autowired
    private PostingService postings;

    @Autowired
    private JobPostingRepository postingRepository;

    @Test
    @DisplayName("새 채용은 설정의 회사 소개 · 복지 · 필수 안내 문구로 공고 초안을 연다")
    void newRecruitmentStartsFromCompanyTemplate() throws Exception {
        TestApi hr = newHr();
        expect(hr.put("/api/companies/me/profile", Map.of("intro", "핀테크 기업이에요.", "culture", "",
                "talents", List.of(), "benefits", List.of("유연 근무"))), 200);
        expect(hr.put("/api/companies/me/posting-settings",
                Map.of("writingStyle", "", "requiredNotices", List.of("채용 일정은 바뀔 수 있어요."))), 200);

        JsonNode posting = json(expect(hr.post("/api/recruitments", null), 201));

        assertThat(posting.path("status").asString()).isEqualTo("DRAFT");
        assertThat(posting.path("content").path("intro").asString()).isEqualTo("핀테크 기업이에요.");
        assertThat(posting.path("content").path("benefits").get(0).asString()).isEqualTo("유연 근무");
        assertThat(posting.path("notices").get(0).asString()).isEqualTo("채용 일정은 바뀔 수 있어요.");
        assertThat(posting.path("stages").get(0).path("type").asString()).isEqualTo("DOCUMENT");
        assertThat(posting.path("documents").get(2).path("required").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("AI 수정안은 적용해야 공고에 반영되고, 전형 절차는 말한 순서와 종류로 정리된다")
    void aiSuggestionChangesPostingOnlyAfterApply() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";

        JsonNode answer = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 코딩테스트, 1차 면접, 임원 면접 순으로 해줘.")), 200));
        assertThat(answer.path("reply").asString()).contains("평가 1개", "면접 2개");
        assertThat(answer.path("stub").asBoolean()).isTrue();
        JsonNode suggestion = answer.path("posting").path("suggestion");
        assertThat(suggestion.path("stages").size()).isEqualTo(4);
        assertThat(suggestion.path("stages").get(1).path("type").asString()).isEqualTo("ASSESSMENT");
        assertThat(answer.path("posting").path("stages").size()).isEqualTo(1);

        JsonNode applied = json(expect(hr.post(base + "/suggestion/apply", null), 200));
        assertThat(applied.path("stages").get(0).path("name").asString()).isEqualTo("서류 전형");
        assertThat(applied.path("stages").get(3).path("name").asString()).isEqualTo("임원 면접");
        assertThat(applied.path("suggestion").isNull()).isTrue();

        JsonNode unclear = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 컬처핏, 면접 순으로 해줘.")), 200));
        assertThat(unclear.path("reply").asString()).contains("컬처핏");
        assertThat(unclear.path("posting").path("suggestion").isNull()).isTrue();

        expect(hr.post(base + "/ai-requests", Map.of("message", "포트폴리오도 필수로 받아줘.")), 200);
        JsonNode withPortfolio = json(expect(hr.post(base + "/suggestion/apply", null), 200));
        assertThat(withPortfolio.path("documents").get(2).path("required").asBoolean()).isTrue();

        expect(hr.post(base + "/ai-requests", Map.of("message", "우대 사항에 결제·정산 경험을 더 구체적으로 써줘")), 200);
        JsonNode discarded = json(expect(hr.post(base + "/suggestion/discard", null), 200));
        assertThat(discarded.path("content").path("preferred").size()).isZero();
    }

    @Test
    @DisplayName("전형별 안내는 첫 전형을 빼고 보여 주고, AI로 전형 절차를 바꿔도 이름이 같은 전형은 안내를 이어 받는다")
    void stageGuidesSurviveStageChanges() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        expect(hr.post(base + "/ai-requests", Map.of("message", "전형은 서류, 1차 면접 순으로 해줘")), 200);
        expect(hr.post(base + "/suggestion/apply", null), 200);
        JsonNode guides = json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200));
        assertThat(guides.size()).isEqualTo(1);
        assertThat(guides.get(0).path("name").asString()).isEqualTo("1차 면접");
        String interview = guides.get(0).path("stageId").asString();

        assertThat(guides.get(0).path("missing").toString())
                .isEqualTo("[\"일정\",\"진행 방식\",\"장소·접속 링크\",\"준비 사항\"]");

        JsonNode saved = json(expect(hr.put("/api/stages/" + interview + "/guide", Map.of("schedule",
                " 11월 3일(화) 오후 2시~4시 ", "method", "대면", "place", "", "preparation", "신분증", "note", "")),
                200));
        assertThat(saved.path("guide").path("schedule").asString()).isEqualTo("11월 3일(화) 오후 2시~4시");
        assertThat(saved.path("missing").toString()).isEqualTo("[\"장소·접속 링크\"]");
        assertThat(saved.path("notifiedCount").asInt()).isZero();

        expect(hr.post(base + "/ai-requests", Map.of("message", "전형은 서류, 코딩테스트, 1차 면접 순으로 해줘")), 200);
        expect(hr.post(base + "/suggestion/apply", null), 200);
        JsonNode changed = json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200));
        assertThat(changed.get(0).path("name").asString()).isEqualTo("코딩테스트");
        assertThat(changed.get(0).path("guide").path("schedule").asString()).isEmpty();
        assertThat(changed.get(1).path("guide").path("method").asString()).isEqualTo("대면");

        String guidePath = "/api/stages/" + changed.get(1).path("stageId").asString() + "/guide";
        expect(hr.put(guidePath, Map.of("schedule", "x".repeat(201), "method", "", "place", "",
                "preparation", "", "note", "")), 400);
        expect(newHr().put(guidePath, Map.of("schedule", "", "method", "", "place", "", "preparation", "",
                "note", "")), 404);
    }

    @Test
    @DisplayName("접수 확인 메일은 기본 문장으로 시작해 게시 전에만 고칠 수 있고, 지원하면 지원자 값을 채워 보낸다")
    void receiptMailIsCheckedBeforePublishing() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        assertThat(draft.path("receipt").path("subject").asString()).isEqualTo("[{회사명}] {공고명} 지원이 접수되었습니다");
        assertThat(draft.path("receipt").path("body").asString()).contains("{지원자명}님", "지원번호 {지원번호}번");
        assertThat(draft.path("receipt").path("requiredText").asString()).startsWith("본 메일은 발신 전용입니다.");

        expect(hr.put(base, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "", "career", "",
                "location", "", "intro", "", "duties", List.of(), "qualifications", List.of(), "preferred", List.of(),
                "benefits", List.of())), 200);
        expect(hr.put(base + "/receipt", Map.of("subject", " ", "body", "본문")), 400);
        JsonNode changed = json(expect(hr.put(base + "/receipt", Map.of("subject", "[{회사명}] 지원 확인",
                "body", "{지원자명}님, {공고명} 지원번호는 {지원번호}번입니다.")), 200));
        assertThat(changed.path("receipt").path("subject").asString()).isEqualTo("[{회사명}] 지원 확인");

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        expect(hr.put(base + "/receipt", Map.of("subject", "바꾼 제목", "body", "바꾼 본문")), 409);

        Map<String, Object> form = TestFixtures.form("receipt@example.com", false);
        form.put("name", "김하늘");
        expect(anonymous().multipart("/api/public/postings/" + draft.path("postingId").asString() + "/applications",
                form), 201);
        assertThat(awaitMail("receipt@example.com")).isEqualTo("receipt@example.com|[테스트 기업] 지원 확인|"
                + "김하늘님, 결제 백엔드 개발자 지원번호는 1번입니다.\n\n본 메일은 발신 전용입니다. 지원자 정보는 채용 목적으로만 이용됩니다.");
    }

    @Test
    @DisplayName("평가 기준은 공고 문장과 짝지어 저장하고, 저장 전에는 더미를 쓰며, 게시하면 기준과 자격요건 · 우대사항이 잠긴다")
    void screeningCriteriaFollowPostingItemsAndLockOnPublish() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        UUID id = UUID.fromString(draft.path("recruitmentId").asString());
        String base = "/api/recruitments/" + id + "/posting";
        Map<String, Object> content = new HashMap<>(Map.of("title", "결제 백엔드 개발자", "jobCategory", "",
                "employmentType", "", "career", "", "location", "", "intro", "", "duties", List.of("결제 API 개발"),
                "qualifications", List.of("Java 서버 개발 경력 3년 이상", "SQL 작성 경험"),
                "preferred", List.of("결제 도메인 경험"), "benefits", List.of()));
        expect(hr.put(base, content), 200);
        UUID companyId = postingRepository.findAll().stream()
                .filter(posting -> posting.getRecruitmentId().equals(id))
                .findFirst().orElseThrow().getCompanyId();

        JsonNode empty = json(expect(hr.get(base + "/criteria"), 200));
        assertThat(empty.path("locked").asBoolean()).isFalse();
        assertThat(empty.path("hireCount").isNull()).isTrue();
        assertThat(empty.path("items").size()).isEqualTo(3);
        assertThat(empty.path("items").get(2).path("criterion").path("criterionId").asString()).isEqualTo("P-01");
        assertThat(empty.path("items").get(0).path("saved").asBoolean()).isFalse();
        assertThat(postings.screeningRubric(companyId, id).criteriaVersion()).startsWith("dummy");

        Map<String, Object> java = criterion("QUALIFICATION", "Java 서버 개발 경력 3년 이상", true, "CONDITION", null);
        Map<String, Object> sql = criterion("QUALIFICATION", "SQL 작성 경험", false, "COMPOSITE", null);
        expect(hr.put(base + "/criteria", Map.of("hireCount", 2, "criteria", List.of(java, sql))), 400);
        expect(hr.put(base + "/criteria", Map.of("hireCount", 2,
                "criteria", List.of(criterion("PREFERENCE", "공고에 없는 문장", false, "SINGLE", null)))), 400);
        expect(hr.put(base + "/criteria", Map.of("hireCount", 0, "criteria", List.of(java))), 400);

        sql.put("partial", "SQL은 썼지만 스키마 설계는 드러나지 않는다");
        JsonNode saved = json(expect(hr.put(base + "/criteria", Map.of("hireCount", 2, "criteria", List.of(java, sql))),
                200));
        assertThat(saved.path("criteriaVersion").asString()).isEqualTo("v1");
        assertThat(saved.path("items").get(0).path("saved").asBoolean()).isTrue();
        assertThat(saved.path("items").get(2).path("saved").asBoolean()).isFalse();
        ScreeningRubric rubric = postings.screeningRubric(companyId, id);
        assertThat(rubric.hireCount()).isEqualTo(2);
        assertThat(rubric.criteria()).extracting(ScreeningRubric.Criterion::criterionId)
                .containsExactly("Q-01", "Q-02");
        assertThat(rubric.criteria().get(0).important()).isTrue();
        assertThat(rubric.criteria().get(1).evaluationRules().partial()).isEqualTo("SQL은 썼지만 스키마 설계는 드러나지 않는다");

        // 문장 순서를 바꾸면 항목 번호가 따라가고, 고친 문장은 기준을 잃는다
        content.put("qualifications", List.of("SQL 작성 경험", "Java 서버 개발 경력 5년 이상"));
        expect(hr.put(base, content), 200);
        JsonNode reordered = json(expect(hr.get(base + "/criteria"), 200));
        assertThat(reordered.path("items").get(0).path("criterion").path("criterionId").asString()).isEqualTo("Q-01");
        assertThat(reordered.path("items").get(0).path("saved").asBoolean()).isTrue();
        assertThat(reordered.path("items").get(1).path("saved").asBoolean()).isFalse();
        assertThat(postings.screeningRubric(companyId, id).criteria())
                .extracting(ScreeningRubric.Criterion::text).containsExactly("SQL 작성 경험");

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        assertThat(json(expect(hr.get(base + "/criteria"), 200)).path("locked").asBoolean()).isTrue();
        expect(hr.put(base + "/criteria", Map.of("hireCount", 3, "criteria", List.of(sql))), 409);
        content.put("preferred", List.of("결제 도메인 경험", "정산 경험"));
        assertThat(expect(hr.put(base, content), 409).body()).contains("REQUIREMENTS_LOCKED");
        expect(hr.post(base + "/ai-requests", Map.of("message", "우대 사항에 정산 경험을 더해줘")), 200);
        assertThat(expect(hr.post(base + "/suggestion/apply", null), 409).body()).contains("REQUIREMENTS_LOCKED");
        content.put("preferred", List.of("결제 도메인 경험"));
        content.put("title", "결제 백엔드 개발자 (경력)");
        expect(hr.put(base, content), 200);
    }

    private static Map<String, Object> criterion(String category, String text, boolean important, String type,
            String partial) {
        Map<String, Object> item = new HashMap<>();
        item.put("category", category);
        item.put("text", text);
        item.put("important", important);
        item.put("criterionType", type);
        item.put("met", text + "을 서류에서 확인할 수 있다");
        item.put("partial", partial);
        item.put("unmet", text + "이 서류에서 확인되지 않는다");
        item.put("certificates", List.of());
        item.put("ncsUnitCode", null);
        return item;
    }

    /** 접수 확인 메일은 접수가 끝난 뒤 따로 보내져 잠깐 기다린다. */
    private String awaitMail(String to) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(10));
        while (Instant.now().isBefore(deadline)) {
            for (String sent : mail.sent) {
                if (sent.startsWith(to + "|")) {
                    return sent;
                }
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Receipt mail was not sent.");
    }

    @Test
    @DisplayName("게시하면 채용 페이지가 열리고 전형 구성은 잠기며, 마감하면 첫 전형이 시작된다")
    void publishOpensCareersPageAndCloseStartsFirstStage() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String id = draft.path("recruitmentId").asString();
        String postingId = draft.path("postingId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        JsonNode content = draft.path("content");
        expect(hr.put(base, Map.of("title", "백엔드 개발자 (Java/Spring)", "jobCategory", "개발 › 백엔드",
                "employmentType", "정규직", "career", "경력 3년 이상", "location", "서울 강남구",
                "intro", content.path("intro").asString(), "duties", List.of("결제 시스템 개발"),
                "qualifications", List.of("Java 3년 이상"), "preferred", List.of(), "benefits", List.of())), 200);

        expect(anonymous().get("/api/public/postings/" + postingId), 404);
        Instant now = Instant.now();
        JsonNode published = json(expect(hr.post(base + "/publish", Map.of(
                "openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(7, ChronoUnit.DAYS).toString())), 200));
        assertThat(published.path("status").asString()).isEqualTo("PUBLISHED");

        JsonNode careers = json(expect(anonymous().get("/api/public/postings/" + postingId), 200));
        assertThat(careers.path("state").asString()).isEqualTo("OPEN");
        assertThat(careers.path("content").path("title").asString()).isEqualTo("백엔드 개발자 (Java/Spring)");

        JsonNode locked = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 1차 면접 순으로 해줘")), 200));
        assertThat(locked.path("reply").asString()).contains("게시한 공고");

        JsonNode closed = json(expect(hr.post(base + "/close", null), 200));
        assertThat(closed.path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(json(expect(anonymous().get("/api/public/postings/" + postingId), 200))
                .path("state").asString()).isEqualTo("CLOSED");
        expect(newHr().get(base), 404);
    }
}
