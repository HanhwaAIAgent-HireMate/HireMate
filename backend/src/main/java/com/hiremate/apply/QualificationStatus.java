package com.hiremate.apply;

/** 자격요건 75% 통과 판단. 점수와 따로 판단하고, 부분 충족은 0.5개로 센다. 확인 필요 항목에 따라 결과가 갈리면 판단 보류다. */
public enum QualificationStatus {
    PASSED, FAILED, UNDETERMINED
}
