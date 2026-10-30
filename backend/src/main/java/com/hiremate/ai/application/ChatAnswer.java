package com.hiremate.ai.application;

import com.hiremate.screening.SelectionMode;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * AI Chat 응답. 찾기 · 편집이면 selectionChanged가 true이고 화면은 리스트와 선택 지원자를 다시 불러온다.
 *
 * @param reportId 리포트 요청이면 만든 · 찾은 리포트. 화면은 리포트 카드를 띄우고, 누르면 모달로 연다
 */
public record ChatAnswer(ChatPlan.Intent intent, @Schema(nullable = true) SelectionMode mode, String message,
        List<ChatItem> items, List<String> sources, List<String> agents, boolean selectionChanged, boolean stub,
        @Schema(nullable = true) UUID reportId) {
}
