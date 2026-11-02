package com.hiremate.notice;

import com.hiremate.recruit.StageGuide;
import java.util.List;
import java.util.UUID;

/**
 * 다음 전형 안내 메일 화면에서 고치는 전형 안내 하나. missing은 비어 있는 안내 칸 이름(기타 안내 제외)으로
 * 보내기 전에 경고한다. locked는 이 전형을 안내하는 메일(앞 전형의 다음 전형 안내)을 보내기 시작해 더는 고칠 수 없다는 뜻이다.
 * 메일과 안내를 함께 잠가, 실패한 지원자에게 다시 보낼 때도 처음과 같은 안내가 붙는다.
 */
public record StageGuideView(UUID stageId, int seq, String name, StageGuide guide, List<String> missing,
        boolean locked) {
}
