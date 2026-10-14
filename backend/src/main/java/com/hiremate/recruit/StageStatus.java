package com.hiremate.recruit;

/** 전형 진행 상태. ACTIVE에서 결과를 확정하면 CONFIRMED(안내 단계), 전형을 종료하면 DONE이다. */
public enum StageStatus {
    PENDING,
    ACTIVE,
    CONFIRMED,
    DONE
}
