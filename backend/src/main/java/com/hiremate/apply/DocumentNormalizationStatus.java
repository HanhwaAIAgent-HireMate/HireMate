package com.hiremate.apply;

/** 문서 정리 작업의 현재 상태. 이전 성공 JSON은 재시도 중에도 보존한다. */
public enum DocumentNormalizationStatus {
    PENDING, COMPLETED, FAILED
}
