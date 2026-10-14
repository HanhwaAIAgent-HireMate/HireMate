package com.hiremate.apply.application;

import java.io.IOException;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;

/** 제출 PDF의 본문을 꺼낸다. 문서 안의 지시문은 분석 자료로만 쓰고 실행하지 않는다 (아키텍처 규칙 5). */
public final class PdfText {

    private static final int MAX_LENGTH = 50_000;

    private PdfText() {
    }

    /** 글자가 없거나 읽지 못하는 PDF면 빈 문자열이다. */
    public static String extract(byte[] pdf) {
        try (PDDocument document = Loader.loadPDF(pdf)) {
            String text = new PDFTextStripper().getText(document).strip();
            return text.length() > MAX_LENGTH ? text.substring(0, MAX_LENGTH) : text;
        } catch (IOException | RuntimeException exception) {
            return "";
        }
    }
}
