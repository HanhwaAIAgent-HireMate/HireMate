package com.hiremate.interview;

/**
 * 지원자 한 명의 실제 면접 진행 상태. 전형 결과·합격 여부와는 별개다.
 * ABSENT는 면접 시간에 오지 않은 지원자다. 같은 시간 면접에서 빼고 나머지 지원자만 시작하고 끝낸다.
 */
public enum InterviewSessionStatus {
    SCHEDULED, IN_PROGRESS, ENDED, ABSENT
}
