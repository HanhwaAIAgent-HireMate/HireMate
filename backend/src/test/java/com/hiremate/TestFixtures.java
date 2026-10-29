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

    private TestFixtures() {
    }

    public static Posting publish(TestApi hr, boolean requirePortfolio) throws Exception {
        return publish(hr, requirePortfolio, null);
    }

    public static Posting publish(TestApi hr, boolean requirePortfolio, String stagePlan) throws Exception {
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String id = draft.path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        expect(hr.put(base, Map.of("title", "백엔드 개발자", "jobCategory", "개발", "employmentType", "정규직",
                "career", "경력 3년 이상", "location", "서울", "intro", "", "duties", List.of("결제 시스템 개발"),
                "qualifications", List.of("Java Spring"), "preferred", List.of(), "benefits", List.of())), 200);
        expect(hr.post(base + "/ai-requests",
                Map.of("message", stagePlan == null ? "전형은 서류, 1차 면접 순으로 해줘" : stagePlan)), 200);
        expect(hr.post(base + "/suggestion/apply", null), 200);
        if (requirePortfolio) {
            expect(hr.post(base + "/ai-requests", Map.of("message", "포트폴리오도 필수로 받아줘")), 200);
            expect(hr.post(base + "/suggestion/apply", null), 200);
        }
        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        return new Posting(id, draft.path("postingId").asString());
    }

    /** 전형의 첫 탭. 전형을 시작하면 탭 1이 생긴다. */
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
