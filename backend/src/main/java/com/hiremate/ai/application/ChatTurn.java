package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 화면에 다시 보여 줄 AI Chat의 지난 턴: 담당자 질문과 그때의 답.
 *
 * @param mentions 질문에 쓴 @멘션. 이 전형에 없는 지원자는 뺀다
 * @param steps 답을 내기까지 거친 처리 단계 문구
 * @param seconds 처리에 걸린 시간. 모르면 null이다
 * @param asker 질문한 담당자. 같은 탭을 함께 쓰는 담당자 가운데 누가 물었는지 보여 준다. 예전 턴은 null이다
 */
public record ChatTurn(String message, List<ChatMention> mentions, ChatAnswer answer, List<String> steps,
        @Schema(nullable = true) Integer seconds, @Schema(nullable = true) ChatAsker asker) {
}
