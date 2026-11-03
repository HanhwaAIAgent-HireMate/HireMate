package com.hiremate.screening;

/**
 * 서류 분포 리포트에서 선 위 지원자의 개수를 세는 기준. 전체 지원자 리스트는 이 기준을 고르지 않고 늘 인재상을 포함한
 * 순서로 선다.
 */
public enum CandidateSort {
    /** 자격요건 + 우대사항에서 충족한 개수. */
    BASIC,
    /** 자격요건 + 우대사항 충족 개수에 상으로 판정한 인재상 개수를 더한 값. */
    TALENT
}
