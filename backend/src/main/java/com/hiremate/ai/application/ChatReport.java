package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * Chat 리포트 요청 (ChatPlan.report). backend가 대상 · 전형을 검증한 뒤 리포트를 만들거나 찾는다.
 *
 * @param stageId STAGE에서 볼 전형. 없으면 현재 전형
 * @param targets COMPARE의 비교 대상 지원서 ID. 현재 전형 지원자만 쓴다
 * @param reportId backend가 만든 · 찾은 리포트. 대화 기록에서 카드를 다시 열 때 쓴다. Root는 비워 둔다
 */
public record ChatReport(Kind kind, @Schema(nullable = true) UUID stageId, List<UUID> targets, String focus,
        boolean brief, @Schema(nullable = true) UUID reportId) {

    /** COMPARE는 현재 전형 지원자 비교, STAGE는 전형 결과 리포트 보기 */
    public enum Kind {
        COMPARE,
        STAGE
    }

    public ChatReport withReport(UUID id) {
        return new ChatReport(kind, stageId, targets, focus, brief, id);
    }
}
