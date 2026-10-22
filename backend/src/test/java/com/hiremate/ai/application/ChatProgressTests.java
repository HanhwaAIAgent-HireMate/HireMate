package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThatCode;

import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ChatProgressTests {

    @Test
    @DisplayName("quiet는 화면 연결이 끊겨 보내지 못해도 예외를 올리지 않는다")
    void quietSwallowsFailures() {
        ChatProgress gone = new ChatProgress() {
            @Override
            public void status(String text) {
                throw new UncheckedIOException(new IOException("Broken pipe"));
            }

            @Override
            public void item(ChatItem item) {
                throw new UncheckedIOException(new IOException("Broken pipe"));
            }
        };
        ChatProgress quiet = ChatProgress.quiet(gone);

        assertThatCode(() -> {
            quiet.status("지원자1 면접 질문을 만들고 있어요");
            quiet.item(new ChatItem(null, "강점", "정산 배치 개선", "OK"));
        }).doesNotThrowAnyException();
    }
}
