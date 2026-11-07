package com.hiremate.file;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Rectangle;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.PDFTextStripperByArea;
import org.apache.pdfbox.text.TextPosition;
import org.junit.jupiter.api.Test;

class PdfTextTests {

    @Test
    void identifiesWhetherSpacesCameFromGlyphGapsOrPdfText() throws Exception {
        byte[] tracked = characterSpaced("CODE", 6);
        byte[] literal = characterSpaced("C O D E", 0);

        assertThat(compact(PdfText.parse(tracked).text())).isEqualTo("C O D E");
        assertThat(compact(PdfText.parse(literal).text())).isEqualTo("C O D E");
        assertThat(glyphText(tracked)).isEqualTo("CODE");
        assertThat(glyphText(literal)).isEqualTo("C O D E");
    }

    @Test
    void separatelyPositionedWordsCanAlsoHaveNoLiteralSpaceGlyph() throws Exception {
        byte[] bytes;
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                showText(content, "BACKEND", 40, 700);
                showText(content, "ENGINEER", 100, 700);
            }
            bytes = save(document);
        }

        assertThat(compact(PdfText.parse(bytes).text())).isEqualTo("BACKEND ENGINEER");
        assertThat(glyphText(bytes)).isEqualTo("BACKENDENGINEER");
    }

    @Test
    void koreanFixtureContainsLiteralSpacesBetweenTitleCharacters() throws Exception {
        Path fixture = Path.of("..", "ai", "tests", "samples", "document_quality_korean.pdf");
        String glyphs = glyphText(Files.readAllBytes(fixture));

        assertThat(glyphs).contains("자  기  소  개  서");
    }

    @Test
    void separatingRegionsReadsIndependentColumnsWithoutChangingTheParser() throws Exception {
        byte[] bytes = sideBySide("Skills", "Career", "Python", "Developer");

        assertThat(compact(PdfText.parse(bytes).text())).isEqualTo("Skills Career Python Developer");
        assertThat(compact(readTwoRegions(bytes)))
                .isEqualTo("Skills Python Career Developer");
    }

    @Test
    void separatingRegionsCannotInferWhetherAdjacentTextFormsTableCells() throws Exception {
        byte[] bytes = sideBySide("Metric", "Before", "Latency", "4.1s");

        assertThat(compact(PdfText.parse(bytes).text())).isEqualTo("Metric Before Latency 4.1s");
        assertThat(compact(readTwoRegions(bytes))).isEqualTo("Metric Latency Before 4.1s");
    }

    @Test
    void separatingRegionsCanBreakSingleColumnLinesAcrossTheBoundary() throws Exception {
        String line = "The applicant built secure backend systems with detailed audit trails for multiple teams.";
        byte[] bytes = singleColumn(line, "Next paragraph follows.");

        assertThat(compact(PdfText.parse(bytes).text())).isEqualTo(line + " Next paragraph follows.");
        assertThat(compact(readTwoRegions(bytes))).isNotEqualTo(line + " Next paragraph follows.");
    }

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

    private static byte[] sideBySide(String leftHeading, String rightHeading,
                                     String leftValue, String rightValue) throws Exception {
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                showText(content, leftHeading, 40, 700);
                showText(content, rightHeading, 350, 700);
                showText(content, leftValue, 40, 670);
                showText(content, rightValue, 350, 670);
            }
            return save(document);
        }
    }

    private static byte[] singleColumn(String firstLine, String secondLine) throws Exception {
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                showText(content, firstLine, 40, 700);
                showText(content, secondLine, 40, 670);
            }
            return save(document);
        }
    }

    private static byte[] characterSpaced(String text, float spacing) throws Exception {
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 10);
                content.setCharacterSpacing(spacing);
                content.newLineAtOffset(40, 700);
                content.showText(text);
                content.endText();
            }
            return save(document);
        }
    }

    private static String glyphText(byte[] bytes) throws Exception {
        try (PDDocument document = Loader.loadPDF(bytes)) {
            GlyphStripper stripper = new GlyphStripper();
            stripper.setSortByPosition(true);
            stripper.getText(document);
            return String.join("", stripper.glyphs);
        }
    }

    private static final class GlyphStripper extends PDFTextStripper {
        private final List<String> glyphs = new ArrayList<>();

        private GlyphStripper() throws IOException {
        }

        @Override
        protected void writeString(String text, List<TextPosition> positions) throws IOException {
            for (TextPosition position : positions) {
                glyphs.add(position.getUnicode());
            }
            super.writeString(text, positions);
        }
    }

    private static void showText(PDPageContentStream content, String text, float x, float y) throws Exception {
        content.beginText();
        content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 10);
        content.newLineAtOffset(x, y);
        content.showText(text);
        content.endText();
    }

    private static String readTwoRegions(byte[] bytes) throws Exception {
        try (PDDocument document = Loader.loadPDF(bytes)) {
            PDFTextStripperByArea stripper = new PDFTextStripperByArea();
            stripper.setSortByPosition(true);
            stripper.addRegion("left", new Rectangle(0, 0, 306, 792));
            stripper.addRegion("right", new Rectangle(306, 0, 306, 792));
            stripper.extractRegions(document.getPage(0));
            return stripper.getTextForRegion("left") + stripper.getTextForRegion("right");
        }
    }

    private static String compact(String text) {
        return text.replaceAll("\\s+", " ").strip();
    }
}
