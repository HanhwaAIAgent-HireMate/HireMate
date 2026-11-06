package com.hiremate.file;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;

class PdfTextTests {

    @Test
    void preservesTextBeyondOldLimitAndPageNumbers() throws Exception {
        try (PDDocument document = new PDDocument()) {
            for (int number = 0; number < 120; number++) {
                PDPage page = new PDPage();
                document.addPage(page);
                try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                    content.beginText();
                    content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 8);
                    content.newLineAtOffset(20, 700);
                    content.showText("Experience ".repeat(50) + "Page " + number);
                    content.endText();
                }
            }
            byte[] bytes = save(document);
            PdfText.Result result = PdfText.parse(bytes);
            assertThat(result.pageCount()).isEqualTo(120);
            assertThat(result.pages()).hasSize(120);
            assertThat(result.pages().getLast().number()).isEqualTo(120);
            assertThat(result.text()).hasSizeGreaterThan(50_000).contains("Page 119");
            assertThat(PdfText.extract(bytes)).isEqualTo(result.text());
            assertThat(result.reviewRequired()).isFalse();
        }
    }

    @Test
    void flagsBlankPageWithoutLosingOtherPages() throws Exception {
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PdfText.Result result = PdfText.parse(save(document));
            assertThat(result.pageCount()).isEqualTo(1);
            assertThat(result.pages().getFirst().issues())
                    .contains("NO_TEXT_OCR_OR_BLANK_PAGE_REVIEW_REQUIRED");
            assertThat(result.reviewRequired()).isTrue();
        }
    }

    @Test
    void reportsUnreadableInputAndKeepsLegacyEmptyText() {
        PdfText.Result result = PdfText.parse(new byte[] {1, 2, 3});
        assertThat(result.issues()).contains("PDF_UNREADABLE_OR_PASSWORD_REQUIRED");
        assertThat(result.reviewRequired()).isTrue();
        assertThat(PdfText.extract(new byte[] {1, 2, 3})).isEmpty();
    }

    private static byte[] save(PDDocument document) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        document.save(output);
        return output.toByteArray();
    }
}
