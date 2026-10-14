package com.hiremate.assessment;

import java.util.List;

/** 직무역량 평가의 NCS 기준 5개 영역 (OI-03 MVP 기본값). */
public final class AssessmentArea {

    public static final List<String> NCS = List.of("의사소통능력", "수리능력", "문제해결능력", "정보능력", "기술능력");

    private AssessmentArea() {
    }
}
