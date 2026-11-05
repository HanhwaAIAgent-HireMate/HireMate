package com.hiremate.notice;

import com.hiremate.recruit.StageGuide;
import com.hiremate.recruit.StageType;
import java.util.List;
import java.util.UUID;

/**
 * 공고 작성 화면의 전형 안내 하나. missing은 비어 있는 안내 칸 이름(기타 안내 제외)으로 게시 전에 경고한다.
 * notifiedCount는 이 전형을 안내하는 메일(앞 전형의 다음 전형 안내)을 받은 지원자 수로,
 * 0보다 크면 안내를 고칠 수 없다. type은 전형 종류로, 면접은 지원자마다 시간을 배정해 안내에 시각을 받지 않는다.
 */
public record StageGuideView(UUID stageId, int seq, String name, StageType type, StageGuide guide,
        List<String> missing, int notifiedCount) {
}
