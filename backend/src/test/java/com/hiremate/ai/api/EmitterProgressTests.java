package com.hiremate.ai.api;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.ai.application.ChatItem;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

class EmitterProgressTests {

    @Test
    @DisplayName("이미 닫힌 스트림(연결 끊김 감지, 제한 시간)에 보내면 화면 연결 끊김으로 알린다")
    void completedEmitterFailsAsGone() {
        SseEmitter emitter = new SseEmitter();
        emitter.complete();
        EmitterProgress progress = new EmitterProgress(emitter);

        assertThatThrownBy(() -> progress.status("요청을 확인하고 있어요")).isInstanceOf(UncheckedIOException.class);
        assertThatThrownBy(() -> progress.item(new ChatItem(null, "강점", "정산 배치 개선", "OK")))
                .isInstanceOf(UncheckedIOException.class);
        assertThatCode(() -> progress.sendQuietly("done", new ChatItem(null, "a", "b", null)))
                .doesNotThrowAnyException();
    }
}
