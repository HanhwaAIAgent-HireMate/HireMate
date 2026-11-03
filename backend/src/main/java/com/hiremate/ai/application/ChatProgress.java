package com.hiremate.ai.application;

import org.slf4j.LoggerFactory;

/**
 * Chat 처리 중 진행 알림. 단계 문구(status)와 검증을 마친 항목(item)만 받는다. 최종 답은 따로 돌려받는다.
 *
 * <p>화면 연결이 끊겨 보내지 못하면 구현이 {@link java.io.UncheckedIOException}을 던진다. 그러면 하던 AI 호출을 멈춘다.
 */
public interface ChatProgress {

    void status(String text);

    /** 깊이가 있는 단계. 깊이를 모르는 구현은 Root 단계로 받는다. */
    default void status(String text, int depth) {
        status(text);
    }

    void item(ChatItem item);

    /** 보내기 실패를 무시한다. Root가 답한 뒤에는 연결이 끊겨도 반영까지 마쳐야 대화 기록과 화면이 어긋나지 않는다. */
    static ChatProgress quiet(ChatProgress progress) {
        return new ChatProgress() {
            @Override
            public void status(String text) {
                ignoringFailure(() -> progress.status(text));
            }

            @Override
            public void status(String text, int depth) {
                ignoringFailure(() -> progress.status(text, depth));
            }

            @Override
            public void item(ChatItem item) {
                ignoringFailure(() -> progress.item(item));
            }
        };
    }

    private static void ignoringFailure(Runnable send) {
        try {
            send.run();
        } catch (RuntimeException gone) {
            // 받을 화면이 없다
            LoggerFactory.getLogger(ChatProgress.class).debug("Chat progress dropped", gone);
        }
    }
}
