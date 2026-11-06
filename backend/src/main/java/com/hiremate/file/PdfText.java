package com.hiremate.file;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.text.PDFTextStripper;

/** 제출 PDF를 페이지별로 읽는다. 원문을 요약하거나 길이로 자르지 않는다. */
public final class PdfText {

    private PdfText() {
    }

    /** 기존 업로드 경로의 본문 추출. 읽지 못한 문서는 빈 문자열이다. */
    public static String extract(byte[] pdf) {
        return parse(pdf).text();
    }

    /** 페이지별 텍스트와 재검토 사유. 텍스트 추출 여부는 내용의 완전성을 보증하지 않는다. */
    public static Result parse(byte[] pdf) {
        try (PDDocument document = Loader.loadPDF(pdf)) {
            if (!document.getCurrentAccessPermission().canExtractContent()) {
                return new Result(0, List.of(), List.of("TEXT_EXTRACTION_NOT_ALLOWED"));
            }
            List<Page> pages = new ArrayList<>();
            for (int number = 1; number <= document.getNumberOfPages(); number++) {
                pages.add(readPage(document, number));
            }
            List<String> issues = pages.isEmpty() ? List.of("NO_PAGES") : List.of();
            return new Result(document.getNumberOfPages(), pages, issues);
        } catch (IOException | RuntimeException exception) {
            return new Result(0, List.of(), List.of("PDF_UNREADABLE_OR_PASSWORD_REQUIRED"));
        }
    }

    private static Page readPage(PDDocument document, int number) {
        try {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(true);
            stripper.setStartPage(number);
            stripper.setEndPage(number);
            String text = stripper.getText(document).strip();
            List<String> issues = new ArrayList<>();
            if (text.isBlank()) {
                issues.add("NO_TEXT_OCR_OR_BLANK_PAGE_REVIEW_REQUIRED");
            }
            if (text.indexOf(0xFFFD) >= 0 || text.indexOf('\0') >= 0) {
                issues.add("SUSPECT_TEXT_ENCODING");
            }
            PDPage page = document.getPage(number - 1);
            if (page.getResources() != null && page.getResources().getXObjectNames().iterator().hasNext()) {
                issues.add("GRAPHICS_OR_IMAGES_REQUIRE_VISUAL_REVIEW");
            }
            return new Page(number, text, issues);
        } catch (IOException | RuntimeException exception) {
            return new Page(number, "", List.of("PAGE_EXTRACTION_FAILED"));
        }
    }

    public record Page(int number, String text, List<String> issues) {
        public Page {
            issues = List.copyOf(issues);
        }
    }

    public record Result(int pageCount, List<Page> pages, List<String> issues) {
        public Result {
            pages = List.copyOf(pages);
            issues = List.copyOf(issues);
        }

        public String text() {
            return pages.stream().map(Page::text).collect(Collectors.joining("\n\n")).strip();
        }

        public boolean reviewRequired() {
            return !issues.isEmpty() || pages.stream().anyMatch(page -> !page.issues().isEmpty());
        }
    }
}
