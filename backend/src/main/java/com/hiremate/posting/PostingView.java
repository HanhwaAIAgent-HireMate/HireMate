package com.hiremate.posting;

import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 공고 편집 화면에 필요한 공고 전체. */
public record PostingView(UUID postingId, UUID recruitmentId, String companyName, RecruitmentStatus status,
        PostingContent content, List<String> notices, List<PostingStage> stages, List<RequiredDocument> documents,
        @Schema(nullable = true) Instant openAt, @Schema(nullable = true) Instant closeAt,
        @Schema(nullable = true) Instant publishedAt, @Schema(nullable = true) Instant closedAt,
        @Schema(nullable = true) PostingSuggestionView suggestion, ReceiptView receipt) {

    public record PostingStage(UUID id, String name, StageType type) {
    }

    /** 접수 확인 메일. 필수 문구는 본문 끝에 붙고 고칠 수 없다. 게시하면 제목 · 본문도 바꿀 수 없다. */
    public record ReceiptView(String subject, String body, String requiredText) {
    }

    /** 적용 전 수정안. 바꾼 칸만 값이 있다. */
    public record PostingSuggestionView(PostingContent content, @Schema(nullable = true) List<PostingStage> stages,
            @Schema(nullable = true) List<RequiredDocument> documents, List<String> changedFields) {
    }
}
