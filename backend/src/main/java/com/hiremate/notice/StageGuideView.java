package com.hiremate.notice;

import com.hiremate.recruit.StageGuide;
import java.util.UUID;

/**
 * 공고 작성 화면의 전형 안내 하나. notifiedCount는 이 전형을 안내하는 메일(앞 전형의 다음 전형 안내)을 받은 지원자 수로,
 * 0보다 크면 안내를 고쳐도 이미 보낸 메일은 바뀌지 않음을 알린다.
 */
public record StageGuideView(UUID stageId, int seq, String name, StageGuide guide, int notifiedCount) {
}
