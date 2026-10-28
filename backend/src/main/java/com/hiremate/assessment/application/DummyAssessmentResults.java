package com.hiremate.assessment.application;

import com.hiremate.assessment.AssessmentArea;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.assessment.AssessmentService.IdentifierType;
import com.hiremate.assessment.AssessmentService.ResultEntry;
import com.hiremate.assessment.ImportResult;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageFinished;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.ClassPathResource;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 평가 전형 결과 더미. 앞 전형을 종료해 평가 전형이 시작되면 넘어온 합격자 모두에게 인적성 적성영역 결과를 입힌다.
 *
 * <p>외부 평가 업체 연동이 없는 시연용이다. 데모 시드 지원자처럼 더미 결과표(TABLE)에 이메일이 있으면 그 값을 쓰고, 없으면
 * 지원서 ID로 점수를 만든다. 같은 지원서는 몇 번을 만들어도 같은 점수다. 결과표 업로드와 같은 경로(importResults)로 넣으므로
 * 총점 정렬 · Assessment Agent 분석 · 전형 결과 확정이 업로드했을 때와 똑같이 움직인다. 평가 전형 대상이 아닌 지원자(앞 전형
 * 불합격자)에게는 넣지 않고, 이미 결과가 있는 지원자는 덮어쓰지 않는다.
 */
@Component
@ConditionalOnProperty(name = "hiremate.dummy.assessment-results.enabled", havingValue = "true")
class DummyAssessmentResults {

    static final String TABLE = "dummy/assessment-results.csv";
    private static final int MIN_SCORE = 55;
    private static final int MAX_SCORE = 98;

    private static final Logger log = LoggerFactory.getLogger(DummyAssessmentResults.class);

    private final AssessmentService assessments;
    private final RecruitService recruits;

    DummyAssessmentResults(AssessmentService assessments, RecruitService recruits) {
        this.assessments = assessments;
        this.recruits = recruits;
    }

    @ApplicationModuleListener
    void on(StageFinished event) {
        Optional<StageInfo> next = next(recruits.getByStage(event.companyId(), event.stageId()).stages(), event);
        if (next.isEmpty() || next.get().type() != StageType.ASSESSMENT) {
            return;
        }
        UUID stageId = next.get().id();
        Map<String, ResultEntry> table = table();
        List<ResultEntry> entries = new ArrayList<>();
        assessments.withoutResults(event.companyId(), stageId).forEach((email, applicationId) ->
                entries.add(table.getOrDefault(email.toLowerCase(Locale.ROOT), generated(email, applicationId))));
        ImportResult imported = assessments.importResults(event.companyId(), stageId, IdentifierType.EMAIL,
                entries, false);
        log.info("Dummy assessment results were added to {} applicants in stage {}", imported.matched(), stageId);
    }

    /** 끝난 전형 바로 다음 전형. 마지막 전형이면 빈 값이다. */
    private static Optional<StageInfo> next(List<StageInfo> stages, StageFinished event) {
        for (int index = 0; index < stages.size() - 1; index++) {
            if (stages.get(index).id().equals(event.stageId())) {
                return Optional.of(stages.get(index + 1));
            }
        }
        return Optional.empty();
    }

    /**
     * 결과표에 없는 지원자의 점수. 지원서 ID를 씨앗으로 영역마다 MIN_SCORE ~ MAX_SCORE 정수를 만들고, 총점은 영역 평균
     * (소수 첫째 자리), 등급은 총점으로 정한다 (90 이상 A · 80 이상 B · 70 이상 C · 그 아래 D).
     */
    static ResultEntry generated(String email, UUID applicationId) {
        Random random = new Random(applicationId.getMostSignificantBits() ^ applicationId.getLeastSignificantBits());
        Map<String, BigDecimal> areas = new LinkedHashMap<>();
        int sum = 0;
        for (String area : AssessmentArea.NCS) {
            int score = MIN_SCORE + random.nextInt(MAX_SCORE - MIN_SCORE + 1);
            areas.put(area, BigDecimal.valueOf(score));
            sum += score;
        }
        BigDecimal total = BigDecimal.valueOf(sum).divide(BigDecimal.valueOf(areas.size()), 1, RoundingMode.HALF_UP);
        return new ResultEntry(email, null, total, areas, grade(total));
    }

    private static String grade(BigDecimal total) {
        double value = total.doubleValue();
        return value >= 90 ? "A" : value >= 80 ? "B" : value >= 70 ? "C" : "D";
    }

    /** 더미 결과표를 이메일(소문자) 순서대로 읽는다. 열 이름은 이메일 · NCS 영역 5개 · 총점 · 등급이고, 빈 점수는 null이다. */
    static Map<String, ResultEntry> table() {
        List<List<String>> rows = TableReader.read(TABLE, read());
        List<String> header = rows.getFirst();
        Map<String, ResultEntry> entries = new LinkedHashMap<>();
        for (List<String> row : rows.subList(1, rows.size())) {
            Map<String, BigDecimal> areas = new LinkedHashMap<>();
            for (String area : AssessmentArea.NCS) {
                areas.put(area, number(cell(row, header, area)));
            }
            String email = cell(row, header, "이메일");
            entries.put(email.toLowerCase(Locale.ROOT), new ResultEntry(email, null,
                    number(cell(row, header, "총점")), areas, cell(row, header, "등급")));
        }
        return entries;
    }

    private static byte[] read() {
        try (InputStream in = new ClassPathResource(TABLE).getInputStream()) {
            return in.readAllBytes();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    private static String cell(List<String> row, List<String> header, String column) {
        int index = header.indexOf(column);
        return index < 0 || index >= row.size() ? "" : row.get(index).trim();
    }

    private static BigDecimal number(String value) {
        return value.isBlank() ? null : new BigDecimal(value);
    }
}
