package com.hiremate.screening;

import java.util.List;
import java.util.UUID;

/**
 * 탭 하나의 선택 지원자. AI Chat이 다른 탭의 선택 지원자(예: 세 탭에 공통으로 있는 지원자)를 가리킬 때 쓴다.
 *
 * @param applicationIds 선택한 순서대로. 결정한 지원자는 넣지 않는다
 */
public record StageTabSelection(UUID id, String name, List<UUID> applicationIds) {
}
