package com.hiremate.ai.application;

import com.hiremate.screening.SelectionMode;
import java.util.List;
import java.util.UUID;

/**
 * Root Agent의 실행 계획. 선택 지원자 변경은 명령(동작, 대상)으로만 담고, 실행은 서버가 검증한 뒤 한다.
 *
 * @param message 답변. {count}는 실제로 반영된 인원, {total}은 전형 전체 인원으로 바뀐다
 */
public record ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
        List<ChatItem> items, List<String> sources, List<String> agents) {

    /** 요청 유형: 지원자 찾기 · 분석과 생성 · 선택 지원자 편집 · 되묻기 · 차단 */
    public enum Intent {
        FIND,
        ANSWER,
        EDIT,
        CLARIFY,
        BLOCKED
    }

    public enum EditAction {
        ADD,
        REMOVE,
        CLEAR,
        RESTORE
    }

    public static ChatPlan answer(Intent intent, String message, List<ChatItem> items, List<String> sources,
            List<String> agents) {
        return new ChatPlan(intent, null, null, List.of(), message, items, sources, agents);
    }
}
