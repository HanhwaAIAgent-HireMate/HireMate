package com.hiremate.ai.application;

import com.hiremate.apply.QualificationStatus;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.ScreeningRubric;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;

/**
 * 지원자 카드의 AI 분석 요약. 모든 항목에 근거 문장과 출처를 붙이고, 근거가 없으면 확인 필요로 둔다 (NFR-03).
 *
 * @param conditions 공고 자격 요건 충족 여부 (칩)
 * @param notable 눈여겨볼 점
 * @param checks 확인이 필요한 점
 * @param holds 총점을 보류한 이유. 보류가 아니면 비어 있다
 * @param criteriaVersion 평가에 쓴 평가 기준 버전
 * @param documentScore 총점(자격요건 + 우대사항, 0~100). 보류면 null
 * @param documentScoreLow 확인 필요를 0점으로 넣어 계산한 총점(보류 점수). 평가하지 못했으면 null. 영역 점수의 *Low도 같다
 * @param qualificationRate 자격요건 충족률(%). 확인 필요가 있으면 null
 * @param qualificationScore 자격요건 점수. 확인 필요가 있으면 null
 * @param preferenceScore 우대사항 점수. 확인 필요가 있으면 null
 * @param criteria 항목별 판정. 분석 전이거나 서류를 읽지 못했으면 비어 있다
 * @param summaries 자기소개서 문항별 요약. 판단 없이 무엇을 썼는지만 담는다
 * @param highlights 문서 Viewer에 표시할 근거 문장
 */
public record CandidateAnalysis(List<Condition> conditions, List<Finding> notable, List<Finding> checks,
        List<Finding> holds, @Schema(nullable = true) String criteriaVersion, ScoreStatus scoreStatus,
        @Schema(nullable = true) BigDecimal documentScore, @Schema(nullable = true) BigDecimal documentScoreLow,
        QualificationStatus qualificationStatus, @Schema(nullable = true) BigDecimal qualificationRate,
        @Schema(nullable = true) BigDecimal qualificationScore,
        @Schema(nullable = true) BigDecimal qualificationScoreLow, int qualificationMax,
        @Schema(nullable = true) BigDecimal preferenceScore, @Schema(nullable = true) BigDecimal preferenceScoreLow,
        int preferenceMax,
        List<CriterionLine> criteria, List<SummarySection> summaries, List<Evidence> highlights, String agent,
        boolean stub) {

    /** 총점 확정 상태. 서류를 읽지 못했거나 확인 필요가 남으면 보류다. */
    public enum ScoreStatus {
        CONFIRMED, HELD
    }

    /** 항목 판정. MET 1 · PARTIAL 0.5(복합 경험형만) · NOT_MET 0이고 UNKNOWN은 판단 불가다. */
    public enum Verdict {
        MET, PARTIAL, NOT_MET, UNKNOWN
    }

    /** 자격증 확인 상태. 증빙 제출을 발급기관 확인으로 표시하지 않는다. */
    public enum CertificateStatus {
        SELF_REPORTED, EVIDENCE_SUBMITTED, ISSUER_VERIFIED
    }

    /**
     * 항목 하나의 판정.
     *
     * @param fulfillment 1 · 0.5 · 0. 확인 필요면 null
     * @param allotted 배점 = 영역 만점 ÷ 영역 항목 수
     * @param earned 획득 점수. 확인 필요면 null
     * @param careerYears 경력 기간 조건이면 요건과 관련된 확인 경력(년)
     * @param certificateStatus 자격증 조건이면 확인 상태
     */
    public record CriterionLine(String criterionId, ScreeningRubric.Category category, String text, boolean important,
            ScreeningRubric.CriterionType criterionType, Verdict verdict,
            @Schema(nullable = true) BigDecimal fulfillment,
            BigDecimal allotted, @Schema(nullable = true) BigDecimal earned, String reason, List<String> satisfiedParts,
            List<String> unsatisfiedParts, List<String> unknownParts, List<Evidence> evidence, int recheckCount,
            @Schema(nullable = true) Integer careerYears,
            @Schema(nullable = true) CertificateStatus certificateStatus) {
    }

    /** 제출 문서의 문항 하나 요약 (지금은 자기소개서 문항마다 하나). */
    public record SummarySection(DocumentType document, String title, String summary, List<String> points,
            List<Evidence> evidence) {
    }

    public record Condition(String label, boolean met, String requirement) {
    }

    public record Finding(String text, String source) {
    }

    public record Evidence(DocumentType document, String sentence) {
    }
}
