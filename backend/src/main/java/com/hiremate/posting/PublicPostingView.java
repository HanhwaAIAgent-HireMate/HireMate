package com.hiremate.posting;

import com.hiremate.recruit.StageIcon;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 지원자용 채용 페이지(APL-01)의 공고. HR이 게시한 내용 그대로다. */
public record PublicPostingView(UUID postingId, String companyName, PostingContent content, List<String> notices,
        List<PublicStage> stages, List<RequiredDocument> documents, Instant openAt, Instant closeAt, State state,
        @Schema(nullable = true) PosterDesign poster) {

    public record PublicStage(String name, StageType type,
            @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) StageIcon icon) {
    }

    /** 접수 전 · 접수 중 · 마감. 마감 후에는 지원하기를 막는다. */
    public enum State {
        UPCOMING,
        OPEN,
        CLOSED
    }
}
