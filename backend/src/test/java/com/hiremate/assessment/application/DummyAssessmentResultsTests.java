package com.hiremate.assessment.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.assessment.AssessmentArea;
import com.hiremate.assessment.AssessmentService.ResultEntry;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class DummyAssessmentResultsTests {

    @Test
    @DisplayName("더미 결과표는 데모 지원자 30명의 NCS 5개 영역 · 총점 · 등급을 읽고, 빈 영역 점수는 null로 둔다")
    void readsDummyTable() {
        Map<String, ResultEntry> table = DummyAssessmentResults.table();

        assertThat(table).hasSize(30);
        ResultEntry dohyun = table.get("dohyun.kim@example.com");
        assertThat(dohyun.areas()).containsOnlyKeys(AssessmentArea.NCS);
        assertThat(dohyun.total()).isEqualByComparingTo("93.8");
        assertThat(dohyun.grade()).isEqualTo("A");
        assertThat(table.get("jiwon.han@example.com").areas().get("문제해결능력")).isNull();
    }

    @Test
    @DisplayName("결과표에 없는 지원자는 지원서 ID로 점수를 만들고, 같은 지원서는 늘 같은 점수다")
    void generatesSameScoresForSameApplication() {
        UUID applicationId = UUID.fromString("3c1f5e2a-7b4d-4e8a-9f60-1a2b3c4d5e6f");

        ResultEntry first = DummyAssessmentResults.generated("new@example.com", applicationId);
        ResultEntry again = DummyAssessmentResults.generated("new@example.com", applicationId);

        assertThat(first).isEqualTo(again);
        assertThat(first.identifier()).isEqualTo("new@example.com");
        assertThat(first.areas()).containsOnlyKeys(AssessmentArea.NCS);
        assertThat(first.areas().values()).allSatisfy(score -> assertThat(score.intValue()).isBetween(55, 98));
        BigDecimal average = first.areas().values().stream().reduce(BigDecimal.ZERO, BigDecimal::add)
                .divide(BigDecimal.valueOf(5), 1, RoundingMode.HALF_UP);
        assertThat(first.total()).isEqualByComparingTo(average);
        assertThat(first.grade()).isIn("A", "B", "C", "D");
    }
}
