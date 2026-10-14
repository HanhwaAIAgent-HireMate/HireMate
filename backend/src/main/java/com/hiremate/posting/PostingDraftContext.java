package com.hiremate.posting;

import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageDraft;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/** AI 수정 요청에 넘기는 현재 공고. */
public record PostingDraftContext(UUID recruitmentId, RecruitmentStatus status, PostingContent content,
        List<StageDraft> stages, Set<DocumentType> requiredExtras) {
}
