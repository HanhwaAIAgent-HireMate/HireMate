package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatStatus;
import com.hiremate.ai.application.PostingAiService;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PostingFocus;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.io.UncheckedIOException;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 공고 편집 화면의 [AI 수정 요청]. 수정안은 HR이 적용해야 공고에 반영된다.
 *
 * <p>SSE로 답한다. 처리 중 단계(status)를 먼저 보내고 done에 답을 보낸다. 실패는 error 이벤트다.
 * 입력이 틀리면 스트림을 열기 전에 오류 응답(JSON)으로 답한다.
 */
@RestController
public class PostingAiController {

    private static final Logger log = LoggerFactory.getLogger(PostingAiController.class);
    // 시간 제한 없음 (서블릿 규약에서 0 이하). 진행은 화면에 보이고, 화면이 떠나면 연결 끊김으로 멈춘다
    private static final long NO_TIMEOUT = 0L;

    private final PostingAiService service;
    private final Executor executor;

    public PostingAiController(PostingAiService service, @Qualifier("chatExecutor") Executor executor) {
        this.service = service;
        this.executor = executor;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/ai-requests")
    @ApiResponse(responseCode = "200", description = "SSE. status · done · error 이벤트",
            content = @Content(mediaType = MediaType.TEXT_EVENT_STREAM_VALUE, schema = @Schema(oneOf = {
                    ChatStatus.class, PostingAiService.PostingAiAnswer.class, ChatController.ChatError.class})))
    public SseEmitter request(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PostingAiRequest request) {
        UUID companyId = member.companyId();
        SseEmitter emitter = new SseEmitter(NO_TIMEOUT);
        executor.execute(() -> answer(emitter, companyId, recruitmentId, request));
        return emitter;
    }

    private void answer(SseEmitter emitter, UUID companyId, UUID recruitmentId, PostingAiRequest request) {
        EmitterProgress progress = new EmitterProgress(emitter);
        try {
            progress.sendQuietly("done",
                    service.request(companyId, recruitmentId, request.message(), request.focus(), progress));
        } catch (UncheckedIOException gone) {
            log.info("Posting AI client disconnected before the answer: recruitment {}", recruitmentId);
        } catch (ApiException exception) {
            progress.sendQuietly("error",
                    new ChatController.ChatError(exception.status().value(), exception.code()));
        } catch (RuntimeException exception) {
            log.error("Posting AI request failed: recruitment {}", recruitmentId, exception);
            progress.sendQuietly("error",
                    new ChatController.ChatError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "INTERNAL_ERROR"));
        }
        emitter.complete();
    }

    /** focus는 HR이 줄을 골라 요청할 때만 있고 아니면 null이다. 있으면 AI는 그 줄만 고친다. */
    public record PostingAiRequest(@NotBlank @Size(max = 1000) String message,
            @Valid @Schema(nullable = true) PostingFocus focus) {
    }
}
