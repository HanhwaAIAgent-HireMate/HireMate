package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatStatus;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PosterProposal;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
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

/** 포스터 요청에도 공고 편집과 같은 처리 과정 스트림을 보낸다. */
@RestController
public class PosterStreamController {
    private static final Logger log = LoggerFactory.getLogger(PosterStreamController.class);
    private final PosterAiController controller;
    private final Executor executor;

    public PosterStreamController(PosterAiController controller, @Qualifier("chatExecutor") Executor executor) {
        this.controller = controller;
        this.executor = executor;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/ai-requests/stream")
    @ApiResponse(responseCode = "200", description = "SSE. status · done · error 이벤트",
            content = @Content(mediaType = MediaType.TEXT_EVENT_STREAM_VALUE, schema = @Schema(oneOf = {
                    ChatStatus.class, PosterProposal.class, ChatController.ChatError.class})))
    public SseEmitter request(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PosterAiController.PosterAiRequest request, HttpSession session) {
        SseEmitter emitter = new SseEmitter(0L);
        executor.execute(() -> answer(emitter, member, recruitmentId, request, session));
        return emitter;
    }

    private void answer(SseEmitter emitter, AuthenticatedMember member, UUID recruitmentId,
            PosterAiController.PosterAiRequest request, HttpSession session) {
        EmitterProgress progress = new EmitterProgress(emitter);
        try {
            PosterProposal proposal = controller.designWithProgress(member, recruitmentId, request,
                    session, progress::status);
            progress.sendQuietly("done", proposal);
        } catch (UncheckedIOException gone) {
            log.info("Poster client disconnected: recruitment {}", recruitmentId);
        } catch (ApiException exception) {
            progress.sendQuietly("error",
                    new ChatController.ChatError(exception.status().value(), exception.code()));
        } catch (RuntimeException exception) {
            log.error("Poster request failed: recruitment {}", recruitmentId, exception);
            progress.sendQuietly("error",
                    new ChatController.ChatError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "INTERNAL_ERROR"));
        }
        emitter.complete();
    }
}
