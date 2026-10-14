package com.hiremate.notice;

/** 초안 확인 중 · 발송 완료 · 일부 실패(다시 보낼 수 있음) · 보낼 대상 없음 */
public enum NoticeStatus {
    DRAFT,
    SENT,
    PARTIAL,
    EMPTY
}
