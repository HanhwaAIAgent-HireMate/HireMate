package com.hiremate.ai.application;

import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * Posting Agent의 서류 평가 기준 초안. 공고 작성 화면의 [평가 기준 AI 초안] · 줄마다 [AI 초안]에서 부른다.
 * 초안은 화면의 입력 칸만 채우고, HR이 고쳐 저장해야 서류 평가 기준이 된다.
 */
public interface PostingCriteriaAgent {

    /**
     * 공고의 자격요건 · 우대사항 한 항목의 유형과 판정 기준.
     *
     * @param ncsUnitCode 저장한 기준에 참고 NCS 능력단위가 있으면 넘긴다. 없으면 null
     */
    CriterionDraft draftCriterion(PostingContent posting, ScreeningRubric.Category category, String text,
            String ncsUnitCode);

    /** 목록마다 '중요'로 추천할 항목(목록의 3분의 1까지)과 근거가 된 주요 업무. */
    ImportantAdvice recommendImportant(PostingContent posting);

    /**
     * 평가 항목 하나의 초안.
     *
     * @param partial 부분 충족 기준. 복합 경험형에만 있다
     * @param certificates 항목 문장에 이름이 있는 자격증
     */
    record CriterionDraft(ScreeningRubric.CriterionType criterionType, String met,
            @Schema(nullable = true) String partial, String unmet, List<String> certificates) {

        public CriterionDraft {
            certificates = certificates == null ? List.of() : List.copyOf(certificates);
        }
    }

    /** 목록마다 '중요' 추천. 추천할 근거가 없는 목록은 비어 있다. */
    record ImportantAdvice(List<ImportantItem> qualifications, List<ImportantItem> preferred) {

        public ImportantAdvice {
            qualifications = qualifications == null ? List.of() : List.copyOf(qualifications);
            preferred = preferred == null ? List.of() : List.copyOf(preferred);
        }
    }

    /**
     * @param index 목록 안 위치 (0부터)
     * @param duty 근거가 된 주요 업무 문장. 공고의 문장 그대로다
     */
    record ImportantItem(int index, String duty) {
    }
}
