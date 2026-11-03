package com.hiremate.screening;

import java.util.UUID;

/**
 * 전형 화면의 탭 하나: 선택 지원자와 AI Chat 대화방의 묶음.
 *
 * @param selectedCount 탭의 선택 지원자 수. 결정한 지원자는 세지 않는다
 */
public record StageTabView(UUID id, String name, long selectedCount) {
}
