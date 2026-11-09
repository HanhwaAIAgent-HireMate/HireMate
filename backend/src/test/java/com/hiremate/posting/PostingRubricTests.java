package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class PostingRubricTests {

    private static final UUID COMPANY = UUID.randomUUID();
    private static final UUID RECRUITMENT = UUID.randomUUID();
    private static final ScreeningRubric.EvaluationRules RULES =
            new ScreeningRubric.EvaluationRules("직접 개발했다", null, "개발 기록이 없다");
    // 더미는 다른 공고의 번호(Q-01)에 중요 표시를 두었다. 이 번호와 표시는 쓰지 않아야 한다
    private static final ScreeningRubric DUMMY = new ScreeningRubric(COMPANY, RECRUITMENT, "v1", 3, List.of(
            new ScreeningRubric.Criterion("Q-01", ScreeningRubric.Category.QUALIFICATION, "Java 서버 개발 경력 3년 이상",
                    true, ScreeningRubric.CriterionType.CONDITION, RULES, List.of()),
            new ScreeningRubric.Criterion("Q-02", ScreeningRubric.Category.QUALIFICATION, "Python 개발 경험", false,
                    ScreeningRubric.CriterionType.COMPOSITE, RULES, List.of())));

    private static PostingContent content(List<String> qualifications, List<String> preferred) {
        return new PostingContent("AX 담당", "AI", "정규직", "경력 무관", "서울", "소개", List.of("AI 도입"), qualifications,
                preferred, List.of(), null, "", "", "", "");
    }

    @Test
    @DisplayName("항목은 공고 줄마다 공고 순서로 번호를 매기고, 필수 표시는 공고에서 '필수'로 표시한 줄이다")
    void criteriaFollowPostingLinesAndRequiredMarks() {
        PostingContent posting = content(List.of("SQL 데이터 분석 역량", "Python  개발 경험"), List.of("클라우드 배포 경험"));
        RequiredCriteria required = new RequiredCriteria(List.of("Python  개발 경험"), List.of("클라우드 배포 경험"));

        ScreeningRubric rubric = PostingRubric.of(DUMMY, posting, required);

        assertThat(rubric.criteria()).extracting(ScreeningRubric.Criterion::criterionId)
                .containsExactly("Q-01", "Q-02", "P-01");
        assertThat(rubric.criteria()).extracting(ScreeningRubric.Criterion::important)
                .containsExactly(false, true, true);
        // 더미의 Q-01(다른 공고 문장)에 붙은 중요 표시는 따라오지 않는다
        assertThat(rubric.criteria().getFirst().text()).isEqualTo("SQL 데이터 분석 역량");
    }

    @Test
    @DisplayName("같은 글의 더미 항목이 있으면 유형 · 판정 기준을 쓰고, 없으면 판정 기준을 비워 AI가 초안을 만들게 한다")
    void rulesComeFromTheDummyOnlyForTheSameText() {
        PostingContent posting = content(List.of("SQL 데이터 분석 역량", "Python 개발 경험"), List.of());

        ScreeningRubric rubric = PostingRubric.of(DUMMY, posting, RequiredCriteria.NONE);

        ScreeningRubric.Criterion unmatched = rubric.criteria().get(0);
        ScreeningRubric.Criterion matched = rubric.criteria().get(1);
        assertThat(unmatched.evaluationRules()).isEqualTo(PostingRubric.NO_RULES);
        assertThat(unmatched.criterionType()).isEqualTo(ScreeningRubric.CriterionType.SINGLE);
        assertThat(matched.evaluationRules()).isEqualTo(RULES);
        assertThat(matched.criterionType()).isEqualTo(ScreeningRubric.CriterionType.COMPOSITE);
        assertThat(rubric.hireCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("필수 표시가 바뀌면 평가 기준 버전이 바뀌고, 공고에 없는 줄의 표시는 무시한다")
    void versionChangesWithRequiredMarks() {
        PostingContent posting = content(List.of("SQL 데이터 분석 역량"), List.of());

        String none = PostingRubric.of(DUMMY, posting, RequiredCriteria.NONE).criteriaVersion();
        String marked = PostingRubric.of(DUMMY, posting,
                new RequiredCriteria(List.of("SQL 데이터 분석 역량"), List.of())).criteriaVersion();
        String stale = PostingRubric.of(DUMMY, posting,
                new RequiredCriteria(List.of("지운 줄"), List.of())).criteriaVersion();

        assertThat(none).startsWith("v1+").isNotEqualTo(marked);
        assertThat(stale).isEqualTo(none);
    }
}
