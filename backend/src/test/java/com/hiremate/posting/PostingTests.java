package com.hiremate.posting;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.TestMailConfiguration;
import com.hiremate.recruit.StageDraft;
import com.hiremate.recruit.StageType;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
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
    @DisplayName("수정안은 칸마다 적용하거나 되돌릴 수 있고, 남은 칸은 수정안으로 남는다")
    void suggestionIsResolvedPerField() throws Exception {
        TestApi hr = newHr();
        UUID id = UUID.fromString(json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId")
                .asString());
        String base = "/api/recruitments/" + id + "/posting";
        PostingContent before = postings.draftContext(hr.companyId(), id).content();
        PostingContent suggested = new PostingContent("결제 백엔드 개발자", before.jobCategory(),
                before.employmentType(), before.career(), before.location(), before.intro(), List.of("결제 API 개발"),
                List.of("Java 서버 개발 경력 3년 이상"), List.of("정산 시스템 경험"), before.benefits());
        postings.suggest(hr.companyId(), id, new PostingSuggestion(suggested,
                List.of(new StageDraft("서류 전형", StageType.DOCUMENT), new StageDraft("1차 면접", StageType.INTERVIEW)),
                null, List.of("title", "duties", "qualifications", "preferred", "stages")));

        JsonNode applied = json(expect(hr.post(base + "/suggestion/apply",
                Map.of("fields", List.of("preferred", "stages"))), 200));
        assertThat(applied.path("content").path("preferred").get(0).asString()).isEqualTo("정산 시스템 경험");
        assertThat(applied.path("content").path("qualifications").size()).isZero();
        assertThat(applied.path("stages").size()).isEqualTo(2);
        assertThat(applied.path("suggestion").path("changedFields").toString())
                .isEqualTo("[\"title\",\"duties\",\"qualifications\"]");
        assertThat(applied.path("suggestion").path("stages").isNull()).isTrue();

        JsonNode discarded = json(expect(hr.post(base + "/suggestion/discard",
                Map.of("fields", List.of("qualifications"))), 200));
        assertThat(discarded.path("suggestion").path("changedFields").toString()).isEqualTo("[\"title\",\"duties\"]");
        assertThat(discarded.path("content").path("qualifications").size()).isZero();
        expect(hr.post(base + "/suggestion/apply", Map.of("fields", List.of("benefits"))), 400);

        JsonNode rest = json(expect(hr.post(base + "/suggestion/apply", null), 200));
        assertThat(rest.path("content").path("title").asString()).isEqualTo("결제 백엔드 개발자");
        assertThat(rest.path("content").path("duties").get(0).asString()).isEqualTo("결제 API 개발");
        assertThat(rest.path("content").path("preferred").get(0).asString()).isEqualTo("정산 시스템 경험");
        assertThat(rest.path("suggestion").isNull()).isTrue();
    }

    @Test
    @DisplayName("모집 조건(채용 인원 · 직급 · 학력 · 근무 일시 · 급여)을 저장하고 AI 수정안으로 고치며, 지원자 화면에 보여 준다. "
            + "고용 형태와 경력은 정해 둔 값만 받는다")
    void recruitmentConditionsAreSavedAndShown() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        UUID id = UUID.fromString(draft.path("recruitmentId").asString());
        String base = "/api/recruitments/" + id + "/posting";
        assertThat(draft.path("content").path("headcount").isNull()).isTrue();
        assertThat(draft.path("content").path("salary").asString()).isEmpty();

        Map<String, Object> content = new HashMap<>(Map.of("title", "결제 백엔드 개발자", "jobCategory", "",
                "employmentType", "", "career", "", "location", "", "intro", "", "duties", List.of(),
                "qualifications", List.of(), "preferred", List.of(), "benefits", List.of()));
        content.putAll(Map.of("headcount", 3, "position", " 사원~대리 ", "education", "학력 무관",
                "workHours", "주 5일(월~금) 10:00~19:00", "salary", "회사 내규에 따름"));
        JsonNode saved = json(expect(hr.put(base, content), 200)).path("content");
        assertThat(saved.path("headcount").asInt()).isEqualTo(3);
        assertThat(saved.path("position").asString()).isEqualTo("사원~대리");
        content.put("headcount", 0);
        expect(hr.put(base, content), 400);
        content.put("headcount", 3);
        content.put("employmentType", "비정규직");
        expect(hr.put(base, content), 400);
        content.put("employmentType", "파견직");
        assertThat(json(expect(hr.put(base, content), 200)).path("content").path("employmentType").asString())
                .isEqualTo("파견직");
        content.put("career", "3년 차 이상");
        expect(hr.put(base, content), 400);
        content.put("career", "경력 3년 이상");
        assertThat(json(expect(hr.put(base, content), 200)).path("content").path("career").asString())
                .isEqualTo("경력 3년 이상");

        PostingContent current = postings.draftContext(hr.companyId(), id).content();
        PostingContent suggested = new PostingContent(current.title(), current.jobCategory(),
                current.employmentType(), current.career(), current.location(), current.intro(), current.duties(),
                current.qualifications(), current.preferred(), current.benefits(), 5, current.position(),
                current.education(), current.workHours(), current.salary());
        postings.suggest(hr.companyId(), id, new PostingSuggestion(suggested, null, null, List.of("headcount")));
        JsonNode applied = json(expect(hr.post(base + "/suggestion/apply", null), 200)).path("content");
        assertThat(applied.path("headcount").asInt()).isEqualTo(5);
        assertThat(applied.path("salary").asString()).isEqualTo("회사 내규에 따름");

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        JsonNode careers = json(expect(anonymous().get("/api/public/postings/" + draft.path("postingId").asString()),
                200)).path("content");
        assertThat(careers.path("headcount").asInt()).isEqualTo(5);
        assertThat(careers.path("workHours").asString()).isEqualTo("주 5일(월~금) 10:00~19:00");
    }

    @Test
    @DisplayName("서류 필수 조건은 공고에 있는 줄만 저장하고, 줄이 빠지거나 AI 수정안으로 바뀌면 표시도 빠지며, 지원자에게는 보내지 않는다")
    void requiredCriteriaFollowLinesAndStayHidden() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        UUID id = UUID.fromString(draft.path("recruitmentId").asString());
        String base = "/api/recruitments/" + id + "/posting";
        Map<String, Object> content = new HashMap<>(Map.of("title", "결제 백엔드 개발자", "jobCategory", "",
                "employmentType", "", "career", "", "location", "", "intro", "", "duties", List.of("결제 개발"),
                "qualifications", List.of("Java 3년 이상", "학사 이상"), "preferred", List.of("금융 도메인 경험"),
                "benefits", List.of()));
        content.put("requiredQualifications", List.of("Java 3년 이상", "공고에 없는 줄"));
        content.put("requiredPreferred", List.of("금융 도메인 경험"));
        JsonNode required = json(expect(hr.put(base, content), 200)).path("required");
        assertThat(required.path("qualifications")).extracting(JsonNode::asString).containsExactly("Java 3년 이상");
        assertThat(required.path("preferred")).extracting(JsonNode::asString).containsExactly("금융 도메인 경험");

        // 표시를 빼고 보내면 그대로 두고, 본문에서 빠진 줄의 표시만 뺀다
        content.remove("requiredQualifications");
        content.remove("requiredPreferred");
        content.put("preferred", List.of("대용량 트래픽 경험"));
        required = json(expect(hr.put(base, content), 200)).path("required");
        assertThat(required.path("qualifications")).extracting(JsonNode::asString).containsExactly("Java 3년 이상");
        assertThat(required.path("preferred")).isEmpty();

        // AI 수정안으로 그 줄이 바뀌면 표시가 빠진다
        PostingContent current = postings.draftContext(hr.companyId(), id).content();
        PostingContent suggested = new PostingContent(current.title(), current.jobCategory(),
                current.employmentType(), current.career(), current.location(), current.intro(), current.duties(),
                List.of("Java · Spring 3년 이상", "학사 이상"), current.preferred(), current.benefits(),
                current.headcount(), current.position(), current.education(), current.workHours(), current.salary());
        postings.suggest(hr.companyId(), id, new PostingSuggestion(suggested, null, null, List.of("qualifications")));
        assertThat(json(expect(hr.post(base + "/suggestion/apply", null), 200)).path("required")
                .path("qualifications")).isEmpty();

        content.put("qualifications", List.of("Java · Spring 3년 이상", "학사 이상"));
        content.put("requiredQualifications", List.of("학사 이상"));
        content.put("requiredPreferred", List.of());
        expect(hr.put(base, content), 200);
        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        JsonNode careers = json(expect(anonymous().get("/api/public/postings/" + draft.path("postingId").asString()),
                200));
        assertThat(careers.has("required")).isFalse();
        assertThat(careers.path("content").has("requiredQualifications")).isFalse();
        assertThat(json(expect(hr.get(base), 200)).path("required").path("qualifications"))
                .extracting(JsonNode::asString).containsExactly("학사 이상");
    }

    @Test
    @DisplayName("HR이 전형 절차를 직접 정하면 그 순서와 종류로 저장하고 안내는 이름으로 이어 받으며, 게시하면 잠긴다")
    void hrEditsStagesDirectly() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String id = draft.path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        JsonNode saved = json(expect(hr.put(base + "/stages", Map.of("stages", List.of(
                stage(" 서류 전형 ", "DOCUMENT"), stage("코딩테스트", "ASSESSMENT"), stage("1차 면접", "INTERVIEW")))), 200));
        assertThat(saved.path("stages").get(0).path("name").asString()).isEqualTo("서류 전형");
        assertThat(saved.path("stages").get(1).path("type").asString()).isEqualTo("ASSESSMENT");
        String coding = saved.path("stages").get(1).path("id").asString();
        expect(hr.put("/api/stages/" + coding + "/guide", Map.of("schedule", day(5), "method", "ONLINE",
                "place", "", "preparation", "", "note", "")), 200);

        JsonNode moved = json(expect(hr.put(base + "/stages", Map.of("stages", List.of(stage("서류 전형", "DOCUMENT"),
                stage("1차 면접", "INTERVIEW"), stage("코딩테스트", "ASSESSMENT")))), 200));
        assertThat(moved.path("stages").get(2).path("name").asString()).isEqualTo("코딩테스트");
        JsonNode guides = json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200));
        assertThat(guides.get(1).path("name").asString()).isEqualTo("코딩테스트");
        assertThat(guides.get(1).path("guide").path("schedule").asString()).isEqualTo(day(5));

        assertThat(json(expect(hr.put(base + "/stages", Map.of("stages", List.of(stage("면접", "INTERVIEW"),
                stage("면접", "INTERVIEW")))), 400)).path("code").asString()).isEqualTo("DUPLICATE_STAGE_NAME");
        expect(hr.put(base + "/stages", Map.of("stages", List.of())), 400);
        expect(hr.put(base + "/stages", Map.of("stages", List.of(stage(" ", "DOCUMENT")))), 400);
        expect(newHr().put(base + "/stages", Map.of("stages", List.of(stage("서류", "DOCUMENT")))), 404);

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        expect(hr.put(base + "/stages", Map.of("stages", List.of(stage("서류 전형", "DOCUMENT")))), 409);
    }

    @Test
    @DisplayName("게시한 공고는 본문과 수정안을 바꿀 수 없고 AI 요청에는 바로 안내하며, 전형별 안내만 고칠 수 있다")
    void publishedPostingIsLocked() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        Map<String, Object> content = Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "",
                "career", "", "location", "", "intro", "", "duties", List.of(), "qualifications", List.of("SQL 경험"),
                "preferred", List.of(), "benefits", List.of());
        expect(hr.put(base, content), 200);
        expect(hr.put(base + "/stages", Map.of("stages", List.of(stage("서류 전형", "DOCUMENT"),
                stage("1차 면접", "INTERVIEW")))), 200);
        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);

        assertThat(json(expect(hr.put(base, content), 409)).path("code").asString()).isEqualTo("RECRUITMENT_LOCKED");
        JsonNode answer = json(expect(hr.post(base + "/ai-requests", Map.of("message", "우대 사항 써 줘")), 200));
        assertThat(answer.path("reply").asString()).startsWith("게시한 공고는 바꿀 수 없어요.");
        assertThat(answer.path("posting").path("suggestion").isNull()).isTrue();
        String guide = "/api/stages/" + json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200))
                .get(0).path("stageId").asString() + "/guide";
        expect(hr.put(guide, Map.of("schedule", day(12), "method", "OFFLINE", "place", "본사 5층",
                "preparation", "", "note", "")), 200);
    }

    @Test
    @DisplayName("HR이 고른 줄만 AI에게 맡기고, 공고에 없는 줄을 고르면 다시 고르게 한다")
    void aiRevisesOnlyTheChosenLine() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        expect(hr.put(base, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "",
                "career", "", "location", "", "intro", "", "duties", List.of(), "qualifications", List.of(),
                "preferred", List.of("금융 도메인 경험", "대용량 트래픽 처리 경험"), "benefits", List.of())), 200);

        JsonNode answer = json(expect(hr.post(base + "/ai-requests", Map.of("message", "이 줄 지워 줘",
                "focus", Map.of("field", "preferred", "index", 0))), 200));
        JsonNode suggestion = answer.path("posting").path("suggestion");
        assertThat(suggestion.path("changedFields").toString()).isEqualTo("[\"preferred\"]");
        assertThat(suggestion.path("content").path("preferred").toString()).isEqualTo("[\"대용량 트래픽 처리 경험\"]");

        JsonNode missing = json(expect(hr.post(base + "/ai-requests", Map.of("message", "고쳐 줘",
                "focus", Map.of("field", "preferred", "index", 2))), 200));
        assertThat(missing.path("reply").asString()).startsWith("고른 줄을 공고에서 찾지 못했어요.");
        expect(hr.post(base + "/ai-requests", Map.of("message", "고쳐 줘",
                "focus", Map.of("field", "title", "index", 0))), 400);
        expect(hr.post(base + "/ai-requests", Map.of("message", "고쳐 줘",
                "focus", Map.of("field", "preferred", "index", -1))), 400);
    }

    @Test
    @DisplayName("전형별 안내는 날짜 형식 · 지난 날짜 · 앞뒤 전형 순서 · 진행 방식에 맞지 않는 장소를 막는다")
    void stageGuideRejectsMismatchedInput() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        expect(hr.put("/api/recruitments/" + id + "/posting/stages", Map.of("stages", List.of(
                stage("서류 전형", "DOCUMENT"), stage("코딩테스트", "ASSESSMENT"), stage("1차 면접", "INTERVIEW")))), 200);
        JsonNode guides = json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200));
        String coding = "/api/stages/" + guides.get(0).path("stageId").asString() + "/guide";
        String interview = "/api/stages/" + guides.get(1).path("stageId").asString() + "/guide";

        assertThat(guideError(hr, coding, Map.of("schedule", day(-1)))).isEqualTo("GUIDE_DATE_PAST");
        expect(hr.put(coding, guide(Map.of("schedule", "2026/11/03"))), 400);
        expect(hr.put(coding, guide(Map.of("schedule", day(5), "method", "OFFLINE", "place", "본사 5층"))), 200);
        assertThat(guideError(hr, interview, Map.of("schedule", day(5)))).isEqualTo("GUIDE_DATE_ORDER");
        assertThat(guideError(hr, interview, Map.of("schedule", day(4)))).isEqualTo("GUIDE_DATE_ORDER");
        assertThat(guideError(hr, interview, Map.of("method", "ONLINE", "place", "meet.example.com")))
                .isEqualTo("GUIDE_LINK_INVALID");
        assertThat(guideError(hr, interview, Map.of("method", "OFFLINE"))).isEqualTo("GUIDE_PLACE_REQUIRED");
        assertThat(guideError(hr, interview, Map.of("place", "본사"))).isEqualTo("GUIDE_METHOD_REQUIRED");
        expect(hr.put(interview, guide(Map.of("preparation", "x".repeat(501)))), 400);

        expect(hr.put(interview, guide(Map.of("schedule", day(7), "method", "ONLINE",
                "place", "https://meet.example.com/abc"))), 200);
        assertThat(guideError(hr, coding, Map.of("schedule", day(8), "method", "OFFLINE", "place", "본사 5층")))
                .isEqualTo("GUIDE_DATE_ORDER");
    }

    /** 오늘에서 며칠 뒤 (YYYY-MM-DD). */
    private static String day(int days) {
        return LocalDate.now().plusDays(days).toString();
    }

    /** 안내 요청 본문. 주지 않은 글 칸은 비우고, 일정 · 진행 방식은 정하지 않은 것(null)으로 둔다. */
    private static Map<String, Object> guide(Map<String, Object> values) {
        Map<String, Object> guide = new HashMap<>(Map.of("place", "", "preparation", "", "note", ""));
        guide.putAll(values);
        return guide;
    }

    private static String guideError(TestApi hr, String path, Map<String, Object> values) throws Exception {
        return json(expect(hr.put(path, guide(values)), 400)).path("code").asString();
    }

    private static Map<String, String> stage(String name, String type) {
        return Map.of("name", name, "type", type);
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

        JsonNode saved = json(expect(hr.put("/api/stages/" + interview + "/guide", Map.of("schedule", day(3),
                "method", "ONLINE", "place", "", "preparation", " 신분증 ", "note", "")), 200));
        assertThat(saved.path("guide").path("schedule").asString()).isEqualTo(day(3));
        assertThat(saved.path("guide").path("preparation").asString()).isEqualTo("신분증");
        assertThat(saved.path("missing").toString()).isEqualTo("[\"장소·접속 링크\"]");
        assertThat(saved.path("notifiedCount").asInt()).isZero();

        expect(hr.post(base + "/ai-requests", Map.of("message", "전형은 서류, 코딩테스트, 1차 면접 순으로 해줘")), 200);
        expect(hr.post(base + "/suggestion/apply", null), 200);
        JsonNode changed = json(expect(hr.get("/api/recruitments/" + id + "/stage-guides"), 200));
        assertThat(changed.get(0).path("name").asString()).isEqualTo("코딩테스트");
        assertThat(changed.get(0).path("guide").path("schedule").isNull()).isTrue();
        assertThat(changed.get(1).path("guide").path("method").asString()).isEqualTo("ONLINE");

        String guidePath = "/api/stages/" + changed.get(1).path("stageId").asString() + "/guide";
        expect(newHr().put(guidePath, Map.of("place", "", "preparation", "", "note", "")), 404);
    }

    @Test
    @DisplayName("접수 확인 메일은 설정의 양식 하나로 모든 공고에 쓰고, 보내는 때의 양식에 지원자 값을 채워 보낸다")
    void receiptMailFollowsCompanySettings() throws Exception {
        TestApi hr = newHr();
        String settings = "/api/companies/me/receipt-template";
        JsonNode template = json(expect(hr.get(settings), 200));
        assertThat(template.path("subject").asString()).isEqualTo("[{회사명}] {공고명} 지원이 접수되었습니다");
        assertThat(template.path("body").asString()).contains("{지원자명}님", "지원번호 {지원번호}번");
        assertThat(template.path("requiredText").asString()).startsWith("본 메일은 발신 전용입니다.");
        assertThat(json(expect(hr.get(settings + "/preview"), 200)).path("html").asString())
                .contains("홍길동님, 테스트 기업 예시 공고 채용에 지원해 주셔서 감사합니다.");

        expect(hr.put(settings, Map.of("subject", " ", "body", "본문")), 400);
        expect(hr.put(settings, Map.of("subject", "[{회사명}] 지원 확인",
                "body", "{지원자명}님, {공고명} 지원번호는 {지원번호}번입니다.")), 200);
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        assertThat(draft.has("receipt")).isFalse();
        expect(hr.put(base, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "", "career", "",
                "location", "", "intro", "", "duties", List.of(), "qualifications", List.of(), "preferred", List.of(),
                "benefits", List.of())), 200);
        JsonNode preview = json(expect(hr.get(base + "/receipt/preview"), 200));
        assertThat(preview.path("subject").asString()).isEqualTo("[테스트 기업] 지원 확인");
        assertThat(preview.path("html").asString()).contains(">지원 확인</div>",
                "홍길동님, 결제 백엔드 개발자 지원번호는 1번입니다.", "본 메일은 발신 전용입니다.");

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        expect(hr.put(settings, Map.of("subject", "[{회사명}] {지원자명}님 지원 확인",
                "body", "{지원자명}님, {공고명}에 지원해 주셔서 감사합니다.")), 200);

        Map<String, Object> form = TestFixtures.form("receipt@example.com", false);
        form.put("name", "김하늘");
        expect(anonymous().multipart("/api/public/postings/" + draft.path("postingId").asString() + "/applications",
                form), 201);
        assertThat(awaitMail("receipt@example.com")).isEqualTo("receipt@example.com|[테스트 기업] 김하늘님 지원 확인|"
                + "김하늘님, 결제 백엔드 개발자에 지원해 주셔서 감사합니다.\n\n본 메일은 발신 전용입니다. 지원자 정보는 채용 목적으로만 이용됩니다.");
        assertThat(mail.html).anySatisfy(html -> assertThat(html).contains(">테스트 기업</td>",
                "김하늘님, 결제 백엔드 개발자에 지원해 주셔서 감사합니다."));
        expect(newHr().get(settings), 200);
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
        assertThat(careers.path("companyAddress").asString()).isEmpty();
        // 회사 주소는 공고 내용이 아니라 회사 정보라, 게시한 뒤에 바꿔도 채용 페이지에 지금 주소가 보인다
        expect(hr.put("/api/companies/me/profile", Map.of("intro", "", "culture", "", "talents", List.of(),
                "benefits", List.of(), "address", "경기도 성남시 분당구 판교역로 1")), 200);
        assertThat(json(expect(anonymous().get("/api/public/postings/" + postingId), 200)).path("companyAddress")
                .asString()).isEqualTo("경기도 성남시 분당구 판교역로 1");
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
