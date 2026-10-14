package com.hiremate.apply;

/** 지원 자료 분석 상태. 실패하면 다시 분석할 수 있다 (NFR-05). */
public enum AnalysisStatus {
    PENDING,
    DONE,
    FAILED
}
