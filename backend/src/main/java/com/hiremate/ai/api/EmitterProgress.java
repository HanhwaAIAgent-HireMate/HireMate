package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.ChatStatus;
import java.io.IOException;
import java.io.UncheckedIOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Chat 스트림에 이벤트를 보낸다. 보내지 못하면(화면 연결 끊김) UncheckedIOException을 던져 하던 AI 호출을 멈추게 한다. */
class EmitterProgress implements ChatProgress {

    private static final Logger log = LoggerFactory.getLogger(EmitterProgress.class);

    private final SseEmitter emitter;

    EmitterProgress(SseEmitter emitter) {
        this.emitter = emitter;
    }

    @Override
    public void status(String text) {
        send("status", new ChatStatus(text, 0));
    }

    @Override
    public void status(String text, int depth) {
        send("status", new ChatStatus(text, depth));
    }

    @Override
    public void item(ChatItem item) {
        send("item", item);
    }

    void send(String name, Object data) {
        try {
            emitter.send(SseEmitter.event().name(name).data(data, MediaType.APPLICATION_JSON));
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        } catch (IllegalStateException completed) {
            // 연결 끊김을 먼저 알았거나 제한 시간이 지나 스트림이 닫혔다. 보내다 끊긴 것과 같다
            throw new UncheckedIOException(new IOException("Chat stream already completed", completed));
        }
    }

    /** 받을 화면이 없으면 버린다. 반영은 이미 마쳤다. */
    void sendQuietly(String name, Object data) {
        try {
            send(name, data);
        } catch (UncheckedIOException gone) {
            log.debug("Chat client gone before {}", name, gone);
        }
    }
}
