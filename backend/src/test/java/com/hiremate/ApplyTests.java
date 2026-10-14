package com.hiremate;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import java.io.ByteArrayOutputStream;
import java.time.Duration;
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
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class ApplyTests extends IntegrationTest {

    @Autowired
    private ApplicationService applications;

    @Test
    @DisplayName("지원서를 접수하면 PDF 본문을 추출해 분석하고, 같은 이메일은 다시 지원할 수 없다")
    void submitsApplicationAndAnalyzesIt() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, false);
        TestApi applicant = anonymous();

        JsonNode submitted = json(expect(applicant.multipart(posting.applyPath(), form("yumin@example.com", true)),
                201));
        assertThat(submitted.path("applicationNo").asInt()).isEqualTo(1);
        expect(applicant.multipart(posting.applyPath(), form("YUMIN@example.com", true)), 409);

        Map<String, Object> missingCoverLetter = form("other@example.com", true);
        missingCoverLetter.remove("coverLetter");
        expect(applicant.multipart(posting.applyPath(), missingCoverLetter), 400);
        Map<String, Object> notPdf = form("third@example.com", true);
        notPdf.put("resume", new TestApi.FilePart("resume.pdf", "application/pdf", new byte[] {1, 2, 3}));
        expect(applicant.multipart(posting.applyPath(), notPdf), 400);

        JsonNode list = json(expect(hr.get("/api/recruitments/" + posting.recruitmentId() + "/applications"), 200));
        assertThat(list.path("total").asLong()).isEqualTo(1);
        assertThat(list.path("items").get(0).path("documents").toString()).contains("RESUME", "COVER_LETTER");
        String applicationId = list.path("items").get(0).path("applicationId").asString();

        ApplicantInfo analyzed = awaitAnalysis(hr.companyId(), posting.recruitmentId());
        assertThat(analyzed.analysisStatus()).isEqualTo(AnalysisStatus.DONE);
        assertThat(analyzed.documentScore()).isNotNull();
        assertThat(applications.detail(hr.companyId(), UUID.fromString(applicationId)).documents().getFirst().text())
                .contains("Java");

        byte[] pdf = hr.getBytes("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME").body();
        assertThat(new String(pdf, 0, 5)).isEqualTo("%PDF-");
        expect(newHr().get("/api/recruitments/" + posting.recruitmentId() + "/applications/" + applicationId
                + "/documents/RESUME"), 404);
    }

    @Test
    @DisplayName("공고에서 필수로 정한 포트폴리오가 없으면 접수하지 않고, 마감한 공고는 받지 않는다")
    void enforcesRequiredPortfolioAndClosedPostings() throws Exception {
        TestApi hr = newHr();
        Posting posting = publish(hr, true);
        TestApi applicant = anonymous();

        expect(applicant.multipart(posting.applyPath(), form("a@example.com", false)), 400);
        expect(applicant.multipart(posting.applyPath(), form("a@example.com", true)), 201);

        expect(hr.post("/api/recruitments/" + posting.recruitmentId() + "/posting/close", null), 200);
        expect(applicant.multipart(posting.applyPath(), form("b@example.com", true)), 409);
    }

    private ApplicantInfo awaitAnalysis(UUID companyId, String recruitmentId) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            List<ApplicantInfo> found = applications.applicants(companyId, UUID.fromString(recruitmentId));
            if (!found.isEmpty() && found.getFirst().analysisStatus() != AnalysisStatus.PENDING) {
                return found.getFirst();
            }
            Thread.sleep(200);
        }
        throw new AssertionError("Analysis did not finish.");
    }

    static Posting publish(TestApi hr, boolean requirePortfolio) throws Exception {
        return publish(hr, requirePortfolio, null);
    }

    static Posting publish(TestApi hr, boolean requirePortfolio, String stagePlan) throws Exception {
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

    static Map<String, Object> form(String email, boolean withPortfolio) throws Exception {
        Map<String, Object> form = new HashMap<>(Map.of("name", "정유민", "email", email, "phone", "010-0000-0000",
                "consentPrivacy", "true", "consentAi", "true",
                "resume", new TestApi.FilePart("이력서.pdf", "application/pdf", pdf("Java Spring payment 5 years")),
                "coverLetter", new TestApi.FilePart("cover.pdf", "application/pdf", pdf("Collaboration story"))));
        if (withPortfolio) {
            form.put("portfolio", new TestApi.FilePart("portfolio.pdf", "application/pdf", pdf("Projects")));
        }
        return form;
    }

    static byte[] pdf(String text) throws Exception {
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

    record Posting(String recruitmentId, String postingId) {

        String applyPath() {
            return "/api/public/postings/" + postingId + "/applications";
        }
    }
}
