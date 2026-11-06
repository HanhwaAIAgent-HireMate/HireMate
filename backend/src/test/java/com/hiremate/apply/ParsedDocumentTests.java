package com.hiremate.apply;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.file.PdfText;
import java.util.List;
import org.junit.jupiter.api.Test;

class ParsedDocumentTests {

    @Test
    void parsesActualPdfAndRetainsAnEmptyPage() throws Exception {
        try (var document = org.apache.pdfbox.Loader.loadPDF(com.hiremate.TestFixtures.pdf("Project experience"))) {
            document.addPage(new org.apache.pdfbox.pdmodel.PDPage());
            var output = new java.io.ByteArrayOutputStream();
            document.save(output);
            ParsedDocument parsed = ParsedDocument.from(PdfText.parse(output.toByteArray()), false);
            assertThat(parsed.pages()).hasSize(2);
            assertThat(parsed.sources()).containsExactly(new DocumentSource("s1", 1, "Project experience"));
            assertThat(parsed.pages().getLast().issues())
                    .containsExactly("NO_TEXT_OCR_OR_BLANK_PAGE_REVIEW_REQUIRED");
        }
    }

    @Test
    void preservesEmptyPagesIssuesAndStableLineSources() {
        PdfText.Result extracted = new PdfText.Result(3, List.of(
                new PdfText.Page(1, "한빛대학교\n학점 4.1/4.5\n프로젝트", List.of()),
                new PdfText.Page(2, "", List.of("NO_TEXT_OCR_OR_BLANK_PAGE_REVIEW_REQUIRED")),
                new PdfText.Page(3, "", List.of("PAGE_EXTRACTION_FAILED"))), List.of());
        ParsedDocument parsed = ParsedDocument.from(extracted, true);
        assertThat(parsed.pages()).hasSize(3);
        assertThat(parsed.pages().get(1).issues()).containsExactly("NO_TEXT_OCR_OR_BLANK_PAGE_REVIEW_REQUIRED");
        assertThat(parsed.pages().get(2).issues()).containsExactly("PAGE_EXTRACTION_FAILED");
        assertThat(parsed.sources()).containsExactly(new DocumentSource("s1", 1, "○○학교"),
                new DocumentSource("s2", 1, "학점 ○○"), new DocumentSource("s3", 1, "프로젝트"));
        assertThat(parsed.pages().get(1).text()).isEmpty();
    }

    @Test
    void preservesLongTextAndDocumentExtractionFailures() {
        String longText = "x".repeat(60_000);
        ParsedDocument parsed = ParsedDocument.from(new PdfText.Result(1,
                List.of(new PdfText.Page(1, longText, List.of())), List.of()), false);
        assertThat(parsed.sources().getFirst().text()).isEqualTo(longText);
        assertThat(ParsedDocument.from(PdfText.parse(new byte[] {1, 2, 3}), false).issues())
                .containsExactly("PDF_UNREADABLE_OR_PASSWORD_REQUIRED");
    }
}
