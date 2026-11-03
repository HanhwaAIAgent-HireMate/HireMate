package com.hiremate.ai.application;

import com.hiremate.posting.DocumentType;
import com.hiremate.posting.ScreeningRubric;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 지원자 카드의 AI 분석 요약. 모든 항목에 근거 문장과 출처를 붙이고, 근거가 없으면 확인 필요로 둔다 (NFR-03).
 * 서류는 점수를 매기지 않는다.
 *
 * @param conditions 공고 자격 요건 충족 여부 (칩)
 * @param notable 눈여겨볼 점
 * @param checks 확인이 필요한 점
 * @param holds 확인 필요로 남은 항목 (서류를 읽지 못했으면 그 사실)
 * @param criteriaVersion 평가에 쓴 평가 기준 버전
 * @param criteria 항목별 판정. 분석 전이거나 서류를 읽지 못했으면 비어 있다
 * @param summaries 자기소개서 문항별 요약. 판단 없이 무엇을 썼는지만 담는다
 * @param highlights 문서 Viewer에 표시할 근거 문장
 */
public record CandidateAnalysis(List<Condition> conditions, List<Finding> notable, List<Finding> checks,
        List<Finding> holds, @Schema(nullable = true) String criteriaVersion,
        List<CriterionLine> criteria, List<SummarySection> summaries, List<Evidence> highlights, String agent,
        boolean stub) {

    /** 항목 판정. PARTIAL은 복합 경험형만 쓰고 UNKNOWN은 판단 불가(확인 필요)다. */
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
     * @param careerYears 경력 기간 조건이면 요건과 관련된 확인 경력(년)
     * @param certificateStatus 자격증 조건이면 확인 상태
     * @param metric 경험형 항목 근거의 정량 지표(원문 그대로). 경험과 지표가 함께 있으면 상, 경험만 있으면 중이다
     */
    public record CriterionLine(String criterionId, ScreeningRubric.Category category, String text, boolean important,
            ScreeningRubric.CriterionType criterionType, Verdict verdict, String reason, List<String> satisfiedParts,
            List<String> unsatisfiedParts, List<String> unknownParts, List<Evidence> evidence, int recheckCount,
            @Schema(nullable = true) Integer careerYears,
            @Schema(nullable = true) CertificateStatus certificateStatus, String metric) {

        public CriterionLine {
            // 지표를 담기 전에 저장한 분석에는 값이 없다
            metric = metric == null ? "" : metric;
        }
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
