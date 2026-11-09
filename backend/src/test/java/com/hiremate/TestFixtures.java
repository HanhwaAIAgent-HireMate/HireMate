package com.hiremate;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;

import java.io.ByteArrayOutputStream;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import tools.jackson.databind.JsonNode;

/** 여러 모듈의 테스트가 같이 쓰는 준비 단계. 공고를 게시하고 지원서 양식을 만든다. */
public final class TestFixtures {

    /** 설정 더미 평가 기준(application.yml)과 같은 글의 자격요건 5줄 · 우대사항 5줄. 앞의 두 자격요건을 필수로 표시한다. */
    public static final List<String> RUBRIC_QUALIFICATIONS = List.of("Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
            "Spring Boot로 REST API를 개발 · 운영한 경험", "MySQL · PostgreSQL 등 RDBMS 스키마 설계와 SQL 작성 경험",
            "Git 기반 코드 리뷰와 협업 경험", "JUnit 등으로 테스트 코드를 작성한 경험");
    public static final List<String> RUBRIC_PREFERRED = List.of("외부 시스템 연동 인터페이스를 설계한 경험",
            "연동 API를 구현하고 오류 · 보안 처리를 적용한 경험", "요구사항을 분석 · 확인해 개발 범위를 정한 경험",
            "빌드 · 배포 자동화(CI/CD)를 구성한 경험", "클래스 · 데이터 모델 등 정적 모델을 설계한 경험");

    private TestFixtures() {
    }

    public static Posting publish(TestApi hr, boolean requirePortfolio) throws Exception {
        return publish(hr, requirePortfolio, null);
    }

    public static Posting publish(TestApi hr, boolean requirePortfolio, String stagePlan) throws Exception {
        return publish(hr, requirePortfolio, stagePlan, false);
    }

    private static Posting publish(TestApi hr, boolean requirePortfolio, String stagePlan, boolean blind)
            throws Exception {
        return publish(hr, requirePortfolio, stagePlan, blind, Map.of());
    }

    private static Posting publish(TestApi hr, boolean requirePortfolio, String stagePlan, boolean blind,
            Map<String, Object> lines) throws Exception {
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String id = draft.path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        Map<String, Object> content = new HashMap<>(Map.of("title", "백엔드 개발자", "jobCategory", "개발",
                "employmentType", "정규직", "career", "경력 3년 이상", "location", "서울", "intro", "",
                "duties", List.of("결제 시스템 개발"), "qualifications", List.of("Java Spring"), "preferred", List.of(),
                "benefits", List.of()));
        content.putAll(lines);
        content.put("blind", blind);
        expect(hr.put(base, content), 200);
        // 빈 전형 절차는 서류 전형 하나로 정한다 (새 공고의 기본 전형 절차와 상관없다)
        if (stagePlan != null && stagePlan.isEmpty()) {
            expect(hr.put(base + "/stages",
                    Map.of("stages", List.of(Map.of("name", "서류 전형", "type", "DOCUMENT")))), 200);
        } else {
            expect(hr.post(base + "/ai-requests",
                    Map.of("message", stagePlan == null ? "전형은 서류, 1차 면접 순으로 해줘" : stagePlan)), 200);
            expect(hr.post(base + "/suggestion/apply", null), 200);
        }
        if (requirePortfolio) {
            expect(hr.post(base + "/ai-requests", Map.of("message", "포트폴리오도 필수로 받아줘")), 200);
            expect(hr.post(base + "/suggestion/apply", null), 200);
        }
        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        return new Posting(id, draft.path("postingId").asString());
    }

    /**
     * 서류 전형 줄 세우기 테스트용 공고: 평가 항목 10개(Q-01 … Q-05, P-01 … P-05)이고 Q-01 · Q-02를 서류 필수 조건으로 표시했다.
     * 기준선은 공고의 필수 표시로 가른다.
     */
    public static Posting publishWithRubricLines(TestApi hr, String stagePlan) throws Exception {
        return publish(hr, false, stagePlan, false, Map.of("qualifications", RUBRIC_QUALIFICATIONS,
                "preferred", RUBRIC_PREFERRED, "requiredQualifications", RUBRIC_QUALIFICATIONS.subList(0, 2)));
    }

    /** 블라인드 채용 공고. */
    public static Posting publishBlind(TestApi hr) throws Exception {
        return publish(hr, false, null, true);
    }

    /** 전형 절차를 정한 블라인드 채용 공고. 빈 절차면 서류 전형 하나다. */
    public static Posting publishBlind(TestApi hr, String stagePlan) throws Exception {
        return publish(hr, false, stagePlan, true);
    }

    /** 전형의 첫 탭. 전형을 시작하면 "새 탭"이 생긴다. */
    public static UUID firstTab(TestApi hr, Object stageId) throws Exception {
        return UUID.fromString(json(expect(hr.get("/api/stages/" + stageId + "/tabs"), 200)).get(0).path("id")
                .asString());
    }

    /** 전형 경로(/api/stages/{id})의 첫 탭 경로. Chat과 선택 지원자는 탭 경로 아래에 있다. */
    public static String firstTabPath(TestApi hr, String stagePath) throws Exception {
        return stagePath + "/tabs/" + json(expect(hr.get(stagePath + "/tabs"), 200)).get(0).path("id").asString();
    }

    public static Map<String, Object> form(String email, boolean withPortfolio) throws Exception {
        Map<String, Object> form = new HashMap<>(Map.of("name", "정유민", "email", email, "phone", "010-0000-0000",
                "consentPrivacy", "true", "consentAi", "true",
                "resume", new TestApi.FilePart("이력서.pdf", "application/pdf", pdf("Java Spring payment 5 years")),
                "coverLetter", new TestApi.FilePart("cover.pdf", "application/pdf", pdf("Collaboration story"))));
        if (withPortfolio) {
            form.put("portfolio", new TestApi.FilePart("portfolio.pdf", "application/pdf", pdf("Projects")));
        }
        return form;
    }

    public static byte[] pdf(String text) throws Exception {
        try (PDDocument document = new PDDocument();
                ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(50, 700);
                content.showText(text);
                content.endText();
            }
            document.save(out);
            return out.toByteArray();
        }
    }

    public record Posting(String recruitmentId, String postingId) {

        public String applyPath() {
            return "/api/public/postings/" + postingId + "/applications";
        }
    }
}
