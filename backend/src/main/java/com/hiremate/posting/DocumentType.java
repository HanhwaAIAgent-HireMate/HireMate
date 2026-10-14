package com.hiremate.posting;

/** 지원서 제출 항목. 이력서 · 자기소개서는 항상 필수이고, 포트폴리오 · 자격증은 공고에서 필수로 정할 수 있다. */
public enum DocumentType {
    RESUME("이력서", "PDF"),
    COVER_LETTER("자기소개서", "PDF"),
    PORTFOLIO("포트폴리오", "PDF"),
    CERTIFICATE("자격증", "텍스트");

    private final String label;
    private final String format;

    DocumentType(String label, String format) {
        this.label = label;
        this.format = format;
    }

    public String label() {
        return label;
    }

    public String format() {
        return format;
    }

    public boolean alwaysRequired() {
        return this == RESUME || this == COVER_LETTER;
    }
}
