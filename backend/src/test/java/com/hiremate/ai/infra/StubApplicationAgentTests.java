package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.apply.CriterionMark;
import com.hiremate.posting.ScreeningRubric;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class StubApplicationAgentTests {

    @Test
    @DisplayName("이력서에 적힌 경력 연수와 첫 회사 이름을 찾는다")
    void readsCareerAndCompany() {
        String resume = "경력\nOO카드 결제플랫폼팀 2021.03 – 현재\nOO시스템 2018.01 - 2021.02";

        assertThat(StubApplicationAgent.careerYears(resume)).isGreaterThanOrEqualTo(5);
        assertThat(StubApplicationAgent.lastCompany(resume)).isEqualTo("OO카드");
        assertThat(StubApplicationAgent.careerYears("저는 경력 6년 차 개발자입니다")).isEqualTo(6);
        assertThat(StubApplicationAgent.careerYears("신입 지원자입니다")).isZero();
    }

    private static ScreeningRubric.Criterion criterion(String id, String text, ScreeningRubric.CriterionType type) {
        return new ScreeningRubric.Criterion(id, ScreeningRubric.Category.QUALIFICATION, text, false, type,
                new ScreeningRubric.EvaluationRules("", null, ""), List.of());
    }

    @Test
    @DisplayName("항목 글의 낱말이 문서에 나오는 비율로 항목마다 판정한다. 서류가 비면 확인 필요다")
    void marksEachCriterionByItsWords() {
        var rubric = new ScreeningRubric(UUID.randomUUID(), UUID.randomUUID(), "v1", 1, List.of(
                criterion("Q-01", "Java Spring 결제", ScreeningRubric.CriterionType.CONDITION),
                criterion("Q-02", "Kafka Redis 대용량 트래픽", ScreeningRubric.CriterionType.COMPOSITE),
                criterion("Q-03", "정산 배치 운영", ScreeningRubric.CriterionType.SINGLE),
                criterion("Q-04", "마케팅 캠페인", ScreeningRubric.CriterionType.SINGLE)));

        var marks = StubApplicationAgent.marks("Java Spring 결제 개발, Kafka Redis 사용, 정산 담당", rubric);

        assertThat(marks).containsEntry("Q-01", CriterionMark.MET).containsEntry("Q-02", CriterionMark.PARTIAL)
                .containsEntry("Q-03", CriterionMark.UNKNOWN).containsEntry("Q-04", CriterionMark.NOT_MET);
        assertThat(StubApplicationAgent.marks("", rubric).values()).containsOnly(CriterionMark.UNKNOWN);
    }
}
