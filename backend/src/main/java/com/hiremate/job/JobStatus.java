package com.hiremate.job;

/** 작업 결과. 실패한 작업은 대상 모듈이 실패로 기록하고 담당자가 다시 요청할 수 있다 (NFR-05). */
public enum JobStatus {
    DONE,
    FAILED
}
