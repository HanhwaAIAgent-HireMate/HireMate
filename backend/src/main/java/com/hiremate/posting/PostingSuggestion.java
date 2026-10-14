package com.hiremate.posting;

import com.hiremate.recruit.StageDraft;
import java.util.List;
import java.util.Set;

/**
 * Posting Agent가 만든 수정안. HR이 적용하기 전까지 공고를 바꾸지 않는다 (FR-03).
 *
 * @param content 수정안을 반영한 본문 전체
 * @param stages 바꾼 전형 절차. 바꾸지 않았으면 null
 * @param requiredExtras 필수로 받을 추가 서류(포트폴리오 · 자격증). 바꾸지 않았으면 null
 * @param changedFields 바뀐 칸 이름. 화면에서 바뀐 부분을 표시한다 (예: preferred, stages, requiredDocuments)
 */
public record PostingSuggestion(PostingContent content, List<StageDraft> stages, Set<DocumentType> requiredExtras,
        List<String> changedFields) {
}
