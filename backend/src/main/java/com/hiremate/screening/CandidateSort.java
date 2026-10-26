package com.hiremate.screening;

/**
 * 서류 전형 전체 지원자 리스트의 정렬 기준. 처음에는 자격요건 순이다. 점수를 보류한 지원자는 범위의 아래쪽 점수로 줄 선다.
 * 평가 · 면접 전형은 이 기준을 쓰지 않고 점수 높은 순이다.
 */
public enum CandidateSort {
    /** 자격요건 점수 높은 순, 같으면 총점 높은 순. */
    QUALIFICATION,
    /** 총점 높은 순, 같으면 자격요건 점수 높은 순. */
    TOTAL
}
