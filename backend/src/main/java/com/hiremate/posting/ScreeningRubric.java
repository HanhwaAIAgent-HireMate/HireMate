package com.hiremate.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * 서류 평가 기준. 공고의 자격요건 · 우대사항마다 유형 · 중요 표시 · 판정 기준을 두고, 선발 인원을 둔다. 서류 점수에서는
 * 영역 안의 항목이 모두 같은 비중이다. 사람이 정해 확정하고 Agent는 항목 · 유형 · 중요 표시를 바꾸지 않는다. 공고 작성 화면에서 입력하기 전까지는
 * 설정(hiremate.dummy.screening-rubric)의 더미를 모든 채용에 쓴다.
 *
 * @param criteriaVersion 평가 기준 버전. 분석 결과에 함께 남고, 바뀌면 저장된 분석 결과를 다시 쓰지 않는다
 * @param hireCount 선발 인원. 서류 전형의 AI 추천은 이 인원의 10배수까지다
 * @param criteria 평가 항목. text는 공고 본문의 자격요건 · 우대사항과 같은 글이어야 짝이 맞는다
 */
public record ScreeningRubric(UUID companyId, UUID recruitmentId, String criteriaVersion, int hireCount,
        List<Criterion> criteria) {

    public ScreeningRubric {
        criteria = criteria == null ? List.of() : List.copyOf(criteria);
    }

    /** 평가 항목의 영역. 영역마다 만점은 50점이다. */
    public enum Category {
        QUALIFICATION, PREFERENCE
    }

    /** 항목 유형. CONDITION(조건형)과 SINGLE(단일 능력 · 경험형)은 0 · 1, COMPOSITE(복합 경험형)는 0 · 0.5 · 1이다. */
    public enum CriterionType {
        CONDITION, SINGLE, COMPOSITE
    }

    /**
     * 평가 항목 하나.
     *
     * @param criterionId 예: Q-01, P-01
     * @param important 중요 표시. 면접 질문을 정리할 때 참고하고 서류 점수에는 쓰지 않는다
     * @param certificates 자격증 보유 조건이면 인정하는 자격증 이름
     */
    public record Criterion(String criterionId, Category category, String text, boolean important,
            CriterionType criterionType, EvaluationRules evaluationRules, List<String> certificates) {

        public Criterion {
            certificates = certificates == null ? List.of() : List.copyOf(certificates);
        }
    }

    /**
     * 판정 기준.
     *
     * @param met 충족(1) 기준
     * @param partial 부분 충족(0.5) 기준. 복합 경험형에만 있다
     * @param unmet 미충족(0) 기준
     */
    public record EvaluationRules(String met, @Schema(nullable = true) String partial, String unmet) {
    }
}
