package com.hiremate.ai.application;

import com.hiremate.screening.SelectionMode;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * AI Chat 응답. 찾기 · 편집이면 selectionChanged가 true이고 화면은 리스트와 선택 지원자를 다시 불러온다.
 */
public record ChatAnswer(ChatPlan.Intent intent, @Schema(nullable = true) SelectionMode mode, String message,
        List<ChatItem> items, List<String> sources, List<String> agents, boolean selectionChanged, boolean stub) {
}
