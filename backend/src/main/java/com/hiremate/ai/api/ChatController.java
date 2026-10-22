package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatAnswer;
import com.hiremate.ai.application.ChatInput;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatService;
import com.hiremate.ai.application.ChatStatus;
import com.hiremate.ai.application.ChatTurn;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.io.UncheckedIOException;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 전형 화면의 AI Chat. 기본 범위는 현재 채용과 전형이고, @멘션과 체크한 지원자로 대상을 좁힌다.
 *
 * <p>질문은 SSE로 답한다. 처리 중 단계(status)와 검증된 항목(item)을 먼저 보내고 마지막 done에 답을 보낸다.
 * 실패는 error 이벤트다. 전형을 찾을 수 없거나 입력이 틀리면 스트림을 열기 전에 오류 응답(JSON)으로 답한다.
 */
@RestController
public class ChatController {

    private static final Logger log = LoggerFactory.getLogger(ChatController.class);
    // ai 서버 응답(60초)과 면접 질문 생성을 기다릴 여유
    private static final Duration STREAM_TIMEOUT = Duration.ofSeconds(120);

    private final ChatService chat;
    private final Executor executor;

    public ChatController(ChatService chat, @Qualifier("chatExecutor") Executor executor) {
        this.chat = chat;
        this.executor = executor;
    }

    @PostMapping("/api/stages/{stageId}/chat")
    @ApiResponse(responseCode = "200", description = "SSE. status · item · done · error 이벤트",
            content = @Content(mediaType = MediaType.TEXT_EVENT_STREAM_VALUE, schema = @Schema(oneOf = {
                    ChatStatus.class, ChatItem.class, ChatAnswer.class, ChatError.class})))
    public SseEmitter chat(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody ChatRequest request) {
        ChatInput input = chat.prepare(member.companyId(), stageId, member.memberId(), request.message(),
                request.mentionIds(), request.checkedIds());
        SseEmitter emitter = new SseEmitter(STREAM_TIMEOUT.toMillis());
        executor.execute(() -> answer(emitter, input));
        return emitter;
    }

    private void answer(SseEmitter emitter, ChatInput input) {
        EmitterProgress progress = new EmitterProgress(emitter);
        try {
            ChatAnswer answer = chat.run(input, progress);
            progress.sendQuietly("done", answer);
        } catch (UncheckedIOException gone) {
            log.info("Chat client disconnected before the answer: stage {}", input.stageId());
        } catch (ApiException exception) {
            progress.sendQuietly("error", new ChatError(exception.status().value(), exception.code()));
        } catch (RuntimeException exception) {
            log.error("Chat failed: stage {}", input.stageId(), exception);
            progress.sendQuietly("error", new ChatError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "INTERNAL_ERROR"));
        }
        emitter.complete();
    }

    /** 담당자의 이 전형 대화 기록. 전형이 끝나면 지워진다. */
    @GetMapping("/api/stages/{stageId}/chat")
    public List<ChatTurn> history(AuthenticatedMember member, @PathVariable UUID stageId) {
        return chat.history(member.companyId(), stageId, member.memberId());
    }

    @DeleteMapping("/api/stages/{stageId}/chat")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void forget(AuthenticatedMember member, @PathVariable UUID stageId) {
        chat.forget(member.companyId(), stageId, member.memberId());
    }

    /** error 이벤트 data. status는 같은 오류를 일반 응답으로 냈을 때의 HTTP 상태다. */
    public record ChatError(int status, String code) {
    }

    public record ChatRequest(@NotBlank @Size(max = 2000) String message,
            @NotNull @Size(max = 20) List<@NotNull UUID> mentionIds,
            @NotNull @Size(max = 500) List<@NotNull UUID> checkedIds) {
    }
}
