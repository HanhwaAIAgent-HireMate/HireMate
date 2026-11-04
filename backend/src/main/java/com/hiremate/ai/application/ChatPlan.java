package com.hiremate.ai.application;

import com.hiremate.screening.SelectionMode;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Root Agent의 실행 계획. 선택 지원자 변경은 명령(동작, 대상)으로만 담고, 실행은 서버가 검증한 뒤 한다.
 *
 * @param message 답변. {count}는 실제로 반영된 인원, {total}은 전형 전체 인원으로 바뀐다
 * @param questionTargets 맞춤 면접 질문을 만들어 카드에 넣을 지원자 (면접 전형)
 * @param questionFocus 지원자별로 Interview Agent에 넘길 확인할 점. 없는 지원자는 HR 문장을 넘긴다
 * @param questionReplace 질문을 만들기 전에 답변 없는 AI 질문을 지우는가. 직접 넣은 질문과 답변을 기록한 질문은 남긴다
 * @param report 리포트 요청 (intent REPORT일 때). backend가 Report Agent에 맡긴 뒤 리포트 ID를 적는다
 * @param questionNcs 면접 질문을 만들 때 NCS를 참고할지. 없으면 SKIP이고 지금처럼 만든다
 */
public record ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
        List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets,
        Map<UUID, String> questionFocus, Map<UUID, InterviewerMemo> questionMemos, boolean questionReplace,
        @Schema(nullable = true) ChatReport report, @Schema(nullable = true) NcsUse questionNcs) {

    public ChatPlan {
        questionMemos = questionMemos == null ? Map.of() : questionMemos;
        questionNcs = questionNcs == null ? NcsUse.SKIP : questionNcs;
    }

    /** NCS 참고 없이 만드는 계획. */
    public ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
            List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets,
            Map<UUID, String> questionFocus, Map<UUID, InterviewerMemo> questionMemos, boolean questionReplace,
            ChatReport report) {
        this(intent, mode, edit, targets, message, items, sources, agents, questionTargets, questionFocus,
                questionMemos, questionReplace, report, NcsUse.SKIP);
    }

    /** 리포트 요청 없이 만드는 계획. */
    public ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
            List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets,
            Map<UUID, String> questionFocus, Map<UUID, InterviewerMemo> questionMemos, boolean questionReplace) {
        this(intent, mode, edit, targets, message, items, sources, agents, questionTargets, questionFocus,
                questionMemos, questionReplace, null);
    }

    public ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
            List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets,
            Map<UUID, String> questionFocus) {
        this(intent, mode, edit, targets, message, items, sources, agents, questionTargets, questionFocus, Map.of());
    }

    public ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
            List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets,
            Map<UUID, String> questionFocus, Map<UUID, InterviewerMemo> questionMemos) {
        this(intent, mode, edit, targets, message, items, sources, agents, questionTargets, questionFocus,
                questionMemos, false);
    }

    /** 확인할 점 없이 만드는 계획. */
    public ChatPlan(Intent intent, SelectionMode mode, EditAction edit, List<UUID> targets, String message,
            List<ChatItem> items, List<String> sources, List<String> agents, List<UUID> questionTargets) {
        this(intent, mode, edit, targets, message, items, sources, agents, questionTargets, Map.of());
    }

    /** 같은 계획에 메시지와 항목만 바꾼다. */
    public ChatPlan with(String message, List<ChatItem> items) {
        return new ChatPlan(intent, mode, edit, targets, message, items, sources, agents, questionTargets,
                questionFocus, questionMemos, questionReplace, report, questionNcs);
    }

    /** 요청 유형: 지원자 찾기 · 분석과 생성 · 선택 지원자 편집 · 리포트 · 되묻기 · 차단 */
    public enum Intent {
        FIND,
        ANSWER,
        EDIT,
        REPORT,
        CLARIFY,
        BLOCKED
    }

    public enum EditAction {
        ADD,
        REMOVE,
        CLEAR
    }

    public static ChatPlan answer(Intent intent, String message, List<ChatItem> items, List<String> sources,
            List<String> agents) {
        return new ChatPlan(intent, null, null, List.of(), message, items, sources, agents, List.of());
    }
}
