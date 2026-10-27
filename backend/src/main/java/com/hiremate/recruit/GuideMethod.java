package com.hiremate.recruit;

/** 전형 진행 방식. 안내 메일에는 label로 쓴다. */
public enum GuideMethod {
    ONLINE("온라인"),
    OFFLINE("오프라인");

    private final String label;

    GuideMethod(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }
}
