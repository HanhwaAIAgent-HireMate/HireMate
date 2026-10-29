package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * ai 서버가 보관한 대화방의 지난 턴 하나.
 *
 * @param plan 그때의 계획. message의 {count}는 대상 수, {total}은 total로 바꿔 보여 준다
 * @param total 그때 전형 인원
 * @param mentions 그때 멘션한 지원자
 * @param steps 그때 화면에 낸 처리 단계 문구. 예전 턴은 비어 있다
 * @param seconds 처리에 걸린 시간. 예전 턴은 null이다
 * @param asker 질문한 담당자. 예전 턴은 null이다
 */
public record ChatHistoryTurn(String message, ChatPlan plan, int total, List<UUID> mentions, List<String> steps,
        @Schema(nullable = true) Integer seconds, @Schema(nullable = true) ChatAsker asker) {

    public ChatHistoryTurn {
        mentions = mentions == null ? List.of() : List.copyOf(mentions);
        steps = steps == null ? List.of() : List.copyOf(steps);
    }

    public ChatHistoryTurn(String message, ChatPlan plan, int total, List<UUID> mentions, List<String> steps,
            Integer seconds) {
        this(message, plan, total, mentions, steps, seconds, null);
    }

    public ChatHistoryTurn(String message, ChatPlan plan, int total) {
        this(message, plan, total, List.of(), List.of(), null, null);
    }
}
