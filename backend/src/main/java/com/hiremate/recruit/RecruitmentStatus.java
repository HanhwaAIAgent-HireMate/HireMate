package com.hiremate.recruit;

/** 채용 진행 상태. 대시보드의 상태 탭과 같다: 작성 중 · 공고 게시 중 · 전형 진행 중 · 종료. */
public enum RecruitmentStatus {
    DRAFT,
    PUBLISHED,
    IN_PROGRESS,
    CLOSED
}
