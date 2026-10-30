package com.hiremate.report;

/** 리포트 작성 상태. PENDING이면 AI 워커가 쓰는 중이다. FAILED면 담당자가 다시 요청할 수 있다. */
public enum AgentReportStatus {
    PENDING,
    DONE,
    FAILED
}
