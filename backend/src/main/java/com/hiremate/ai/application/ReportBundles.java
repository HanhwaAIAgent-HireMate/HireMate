package com.hiremate.ai.application;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.CriterionMark;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateFilter;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * Report Agent에 넘길 묶음을 만든다. 업무 데이터(지원자번호, 결정, 점수, AI 추천, 지표)만 넣고 이름은 넣지 않는다.
 * 분석 판정 · 근거는 ai가 자기 저장소에서 applicationId로 찾아 붙인다 (아키텍처 규칙 3). 서류 항목 판정
 * (document.criterion.{항목})은 지원서에 저장한 판정을 backend가 먼저 넣어, ai 쪽 분석 결과가 없거나 기준이 바뀌어도 그릴 수 있게 한다.
 *
 * <p>서류 전형은 점수 대신 항목 판정으로 본다. 서류 점수(총점, 자격요건 · 우대사항 점수)는 아직 저장되지만 넣지 않는다.
 *
 * <p>값 key는 '{전형 종류}.{항목}'이다 (예: document.ai_pick, assessment.area.문제해결능력). 범위에 같은 종류의 전형이
 * 또 있으면 interview2처럼 번호를 붙인다. ai의 enrich.stage_prefix와 같은 규칙이다.
 */
@Component
public class ReportBundles {

    /** 평가 결과 영역 점수의 만점. 평가 결과표는 영역마다 100점 만점이다. */
    static final double AREA_MAX = 100;

    private static final int PAGE = 200;
    static final int[][] CAREER_BANDS = {{0, 0}, {1, 2}, {3, 4}, {5, 6}, {7, Integer.MAX_VALUE}};
    static final String[] CAREER_LABELS = {"신입", "1~2년", "3~4년", "5~6년", "7년 이상"};

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationService applications;
    private final PostingService postings;
    private final AssessmentService assessments;

    ReportBundles(RecruitService recruits, ScreeningService screening, ApplicationService applications,
            PostingService postings, AssessmentService assessments) {
        this.recruits = recruits;
        this.screening = screening;
        this.applications = applications;
        this.postings = postings;
        this.assessments = assessments;
    }

    /** 지원자번호. 채용 안에서 모든 전형에 같다. */
    public static String number(int applicationNo) {
        return "A-%04d".formatted(applicationNo);
    }

    /**
     * 전형 하나의 묶음. 범위는 그 전형과 앞 전형들이고, 지원자는 그 전형의 지원자 전원이다.
     *
     * @param targets 비교 대상 지원서 ID. 비교 리포트가 아니면 빈 목록. 그 전형의 지원자만 받는다
     */
    public ReportBundle build(UUID companyId, UUID stageId, ReportBundle.Kind kind, Collection<UUID> targets,
            String focus, boolean brief) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo current = recruitment.stage(stageId).orElseThrow();
        List<StageInfo> scope = recruitment.stages().stream().filter(stage -> stage.seq() <= current.seq()).toList();
        List<CandidateRow> rows = rows(companyId, stageId);
        Map<UUID, ApplicantInfo> infos = applications.applicants(companyId,
                rows.stream().map(CandidateRow::applicationId).toList()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, Function.identity()));
        rows = rows.stream().filter(row -> infos.containsKey(row.applicationId())).toList();
        Map<UUID, String> numbers = rows.stream().collect(Collectors.toMap(CandidateRow::applicationId,
                row -> number(infos.get(row.applicationId()).applicationNo())));

        Facts facts = new Facts();
        String prefix = prefix(scope, current);
        ScreeningRubric rubric = postings.screeningRubric(companyId, recruitment.id());
        criteria(facts, scope, rubric, rows, infos, numbers);
        for (CandidateRow row : rows) {
            String number = numbers.get(row.applicationId());
            facts.verdict(number, stageId, prefix + ".decision", current.name() + " 결정", row.decision().name());
            if (current.type() == StageType.DOCUMENT) {
                facts.verdict(number, stageId, "document.ai_pick", "AI 추천",
                        row.aboveLine() ? "RECOMMENDED" : "NOT_RECOMMENDED");
            } else if (current.type() == StageType.ASSESSMENT) {
                assessment(facts, number, companyId, stageId, prefix, row);
            } else if (current.type() == StageType.INTERVIEW && row.score() != null) {
                facts.number(number, stageId, prefix + ".score", current.name() + " 점수", row.score(), null);
            }
        }
        String totalKey = switch (current.type()) {
            case DOCUMENT -> null;
            case ASSESSMENT -> prefix + ".total";
            case INTERVIEW -> facts.has(prefix + ".score") ? prefix + ".score" : null;
        };
        // 서류는 자격요건 · 우대사항 판정을 영역으로 나누고, 평가 · 면접은 점수가 있으면 전형 하나를 영역으로 둔다
        List<ReportBundle.Area> areas = current.type() == StageType.DOCUMENT
                ? documentAreas(rubric)
                : stageArea(current, prefix, facts, companyId, recruitment.id()).stream().toList();
        List<ReportBundle.Applicant> applicants = rows.stream()
                .map(row -> new ReportBundle.Applicant(numbers.get(row.applicationId()), row.applicationId(),
                        row.careerYears(), row.lastCompany()))
                .toList();
        List<String> compared = targets.stream().filter(numbers::containsKey).map(numbers::get).distinct().toList();
        List<ReportBundle.Metric> metrics = metrics(stageId, prefix, totalKey, rows, infos, facts,
                passed(rows, numbers));
        return new ReportBundle(kind, companyId, recruitment.id(), stageId, recruitment.title(), Instant.now(),
                focus == null ? "" : focus, brief, scope.stream().map(ReportBundles::stage).toList(), applicants,
                compared, totalKey, areas, metrics, facts.list, List.of());
    }

    /**
     * 채용 최종 리포트 묶음. 범위는 모든 전형이고, 지원자는 첫 전형의 지원자 전원이다.
     *
     * <p>전형마다 결정({전형}.decision)과 점수를 넣고, 점수가 있는 전형과 서류 전형은 영역 하나로 둔다. 최종 합격자는 마지막 전형의
     * 합격자다. 현재 전형(stageId)은 마지막 전형이다.
     */
    public ReportBundle buildFinal(UUID companyId, UUID recruitmentId) {
        RecruitmentInfo recruitment = recruits.get(companyId, recruitmentId);
        List<StageInfo> scope = recruitment.stages();
        StageInfo last = scope.getLast();
        List<CandidateRow> everyone = rows(companyId, scope.getFirst().id());
        Map<UUID, ApplicantInfo> infos = applications.applicants(companyId,
                everyone.stream().map(CandidateRow::applicationId).toList()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, Function.identity()));
        everyone = everyone.stream().filter(row -> infos.containsKey(row.applicationId())).toList();
        Map<UUID, String> numbers = everyone.stream().collect(Collectors.toMap(CandidateRow::applicationId,
                row -> number(infos.get(row.applicationId()).applicationNo())));

        Facts facts = new Facts();
        criteria(facts, scope, postings.screeningRubric(companyId, recruitmentId), everyone, infos, numbers);
        List<ReportBundle.Metric> metrics = new ArrayList<>();
        List<ReportBundle.Area> areas = new ArrayList<>();
        List<CandidateRow> finalists = List.of();
        metrics.add(metric("m-applicants", null, "지원", everyone.size(), "명", null, null));
        for (StageInfo stage : scope) {
            String prefix = prefix(scope, stage);
            List<CandidateRow> rows = rows(companyId, stage.id()).stream()
                    .filter(row -> numbers.containsKey(row.applicationId())).toList();
            for (CandidateRow row : rows) {
                String number = numbers.get(row.applicationId());
                facts.verdict(number, stage.id(), prefix + ".decision", stage.name() + " 결정", row.decision().name());
                if (stage.type() == StageType.ASSESSMENT) {
                    assessment(facts, number, companyId, stage.id(), prefix, row);
                } else if (stage.type() == StageType.INTERVIEW && row.score() != null) {
                    facts.number(number, stage.id(), prefix + ".score", stage.name() + " 점수", row.score(), null);
                }
            }
            long pass = rows.stream().filter(row -> row.decision() == Decision.PASS).count();
            metrics.add(metric("m-" + prefix + "-target", stage.id(), stage.name() + " 대상", rows.size(), "명", null,
                    null));
            metrics.add(metric("m-" + prefix + "-pass", stage.id(), stage.name() + " 합격", pass, "명", null, null));
            stageArea(stage, prefix, facts, companyId, recruitmentId).ifPresent(areas::add);
            if (stage.equals(last)) {
                finalists = rows.stream().filter(row -> row.decision() == Decision.PASS).toList();
            }
        }
        metrics.add(metric("m-finalists", last.id(), "최종 합격", finalists.size(), "명", null, null));
        if (!everyone.isEmpty()) {
            metrics.add(metric("m-final-rate", null, "최종 합격률", round(100.0 * finalists.size() / everyone.size()),
                    "%", null, null));
        }
        careers(metrics, null, "all", "전체", everyone);
        careers(metrics, last.id(), "final", "최종 합격자", finalists);
        List<ReportBundle.Applicant> applicants = everyone.stream()
                .map(row -> new ReportBundle.Applicant(numbers.get(row.applicationId()), row.applicationId(),
                        row.careerYears(), row.lastCompany()))
                .toList();
        return new ReportBundle(ReportBundle.Kind.FINAL, companyId, recruitment.id(), last.id(), recruitment.title(),
                Instant.now(), "", false, scope.stream().map(ReportBundles::stage).toList(), applicants, List.of(),
                null, areas, metrics, facts.list, List.of());
    }

    /** 전형 하나의 영역. 평가 · 면접은 점수가 있는 전형만 둔다. 서류는 심사 항목 판정만 묶는다 (최종 리포트용). */
    private Optional<ReportBundle.Area> stageArea(StageInfo stage, String prefix, Facts facts, UUID companyId,
            UUID recruitmentId) {
        return switch (stage.type()) {
            case DOCUMENT -> prefix.equals("document")
                    ? Optional.of(new ReportBundle.Area(prefix, stage.name(), null,
                            postings.screeningRubric(companyId, recruitmentId).criteria().stream()
                                    .map(criterion -> "document.criterion." + criterion.criterionId()).toList()))
                    : Optional.empty();
            case ASSESSMENT -> facts.has(prefix + ".total")
                    ? Optional.of(new ReportBundle.Area(prefix, stage.name(), prefix + ".total",
                            facts.keys(prefix + ".area.")))
                    : Optional.empty();
            case INTERVIEW -> facts.has(prefix + ".score")
                    ? Optional.of(new ReportBundle.Area(prefix, stage.name(), prefix + ".score", List.of()))
                    : Optional.empty();
        };
    }

    private List<CandidateRow> rows(UUID companyId, UUID stageId) {
        List<CandidateRow> rows = new ArrayList<>();
        for (int page = 0;; page++) {
            // 리포트는 탭의 선택 표시와 무관하다
            var result = screening.candidates(companyId, stageId, null, null, CandidateFilter.NONE, page, PAGE);
            rows.addAll(result.items());
            if (rows.size() >= result.total() || result.items().isEmpty()) {
                return rows;
            }
        }
    }

    /**
     * 서류 항목 판정. 범위에 첫 서류 전형이 있으면 지원자마다 지원서에 저장한 판정을 지금 평가 기준의 항목만 넣는다.
     * 분석 전이라 판정이 없는 항목은 넣지 않는다.
     */
    private static void criteria(Facts facts, List<StageInfo> scope, ScreeningRubric rubric, List<CandidateRow> rows,
            Map<UUID, ApplicantInfo> infos, Map<UUID, String> numbers) {
        Optional<StageInfo> document = scope.stream().filter(stage -> stage.type() == StageType.DOCUMENT)
                .findFirst();
        if (document.isEmpty()) {
            return;
        }
        for (CandidateRow row : rows) {
            Map<String, CriterionMark> marks = infos.get(row.applicationId()).criterionMarks();
            for (ScreeningRubric.Criterion criterion : rubric.criteria()) {
                CriterionMark mark = marks.get(criterion.criterionId());
                if (mark != null) {
                    facts.verdict(numbers.get(row.applicationId()), document.get().id(),
                            "document.criterion." + criterion.criterionId(),
                            criterion.text(), mark.name());
                }
            }
        }
    }

    private void assessment(Facts facts, String number, UUID companyId, UUID stageId, String prefix, CandidateRow row) {
        assessments.find(companyId, stageId, row.applicationId()).ifPresent(result -> {
            facts.number(number, stageId, prefix + ".total", "평가 총점", result.total(), null);
            result.areas().forEach((area, score) -> facts.number(number, stageId, prefix + ".area." + area, area,
                    score, AREA_MAX));
        });
    }

    private static List<ReportBundle.Area> documentAreas(ScreeningRubric rubric) {
        List<ReportBundle.Area> areas = new ArrayList<>();
        for (ScreeningRubric.Category category : ScreeningRubric.Category.values()) {
            List<String> keys = rubric.criteria().stream().filter(criterion -> criterion.category() == category)
                    .map(criterion -> "document.criterion." + criterion.criterionId()).toList();
            if (keys.isEmpty()) {
                continue;
            }
            boolean qualification = category == ScreeningRubric.Category.QUALIFICATION;
            areas.add(new ReportBundle.Area(category.name().toLowerCase(Locale.ROOT), qualification ? "자격요건" : "우대사항",
                    null, keys));
        }
        return areas;
    }

    private static List<String> passed(List<CandidateRow> rows, Map<UUID, String> numbers) {
        return rows.stream().filter(row -> row.decision() == Decision.PASS).map(row -> numbers.get(row.applicationId()))
                .toList();
    }

    private static List<ReportBundle.Metric> metrics(UUID stageId, String prefix, String totalKey,
            List<CandidateRow> rows, Map<UUID, ApplicantInfo> infos, Facts facts, List<String> passed) {
        List<ReportBundle.Metric> metrics = new ArrayList<>();
        long pass = rows.stream().filter(row -> row.decision() == Decision.PASS).count();
        long fail = rows.stream().filter(row -> row.decision() == Decision.FAIL).count();
        metrics.add(metric("m-target", stageId, "대상", rows.size(), "명", null, null));
        metrics.add(metric("m-pass", stageId, "합격", pass, "명", null, null));
        metrics.add(metric("m-fail", stageId, "불합격", fail, "명", null, null));
        metrics.add(metric("m-pending", stageId, "미결정", rows.size() - pass - fail, "명", null, null));
        if (!rows.isEmpty()) {
            metrics.add(metric("m-pass-rate", stageId, "합격률", round(100.0 * pass / rows.size()), "%", null, null));
        }
        if (totalKey != null) {
            facts.average(totalKey).ifPresent(avg -> metrics.add(metric("m-avg-" + totalKey, stageId,
                    facts.label(totalKey) + " 평균", avg, "점", totalKey, null)));
            facts.average(totalKey, passed)
                    .ifPresent(avg -> metrics.add(metric("m-pass-avg", stageId, "합격자 " + facts.label(totalKey) + " 평균",
                            avg, "점", totalKey, null)));
        }
        if (prefix.equals("document")) {
            Map<CriterionMark, Long> judged = rows.stream().collect(Collectors.groupingBy(
                    row -> required(row, infos.get(row.applicationId())), Collectors.counting()));
            metrics.add(metric("m-req-met", stageId, "필수 조건 충족", judged.getOrDefault(CriterionMark.MET, 0L), "명",
                    null, "required-judgement"));
            metrics.add(metric("m-req-unmet", stageId, "필수 조건 미충족", judged.getOrDefault(CriterionMark.NOT_MET, 0L),
                    "명", null, "required-judgement"));
            metrics.add(metric("m-req-unknown", stageId, "필수 조건 확인 필요",
                    judged.getOrDefault(CriterionMark.UNKNOWN, 0L), "명", null, "required-judgement"));
        }
        careers(metrics, stageId, "all", "전체", rows);
        careers(metrics, stageId, "pass", "합격자", rows.stream().filter(row -> row.decision() == Decision.PASS).toList());
        return metrics;
    }

    /**
     * 필수 조건 판정 하나로 줄인다. 모두 충족이면 MET, 하나라도 미충족 · 부분 충족이면 NOT_MET,
     * 나머지(확인 필요만 남음, 분석 전)는 UNKNOWN이다. 부분 충족은 선 위에 오르지 못하므로 미충족에 센다.
     */
    static CriterionMark required(CandidateRow row, ApplicantInfo info) {
        if (info.analysisStatus() != AnalysisStatus.DONE) {
            return CriterionMark.UNKNOWN;
        }
        if (row.missingRequired().isEmpty()) {
            return CriterionMark.MET;
        }
        boolean unmet = row.missingRequired().stream().map(id -> info.criterionMarks().get(id))
                .anyMatch(mark -> mark == CriterionMark.NOT_MET || mark == CriterionMark.PARTIAL);
        return unmet ? CriterionMark.NOT_MET : CriterionMark.UNKNOWN;
    }

    private static void careers(List<ReportBundle.Metric> metrics, UUID stageId, String group, String label,
            List<CandidateRow> rows) {
        if (rows.isEmpty()) {
            return;
        }
        for (int band = 0; band < CAREER_BANDS.length; band++) {
            int low = CAREER_BANDS[band][0];
            int high = CAREER_BANDS[band][1];
            long count = rows.stream().filter(row -> row.careerYears() != null && row.careerYears() >= low
                    && row.careerYears() <= high).count();
            metrics.add(metric("m-career-%s-%d".formatted(group, band), stageId, label + " " + CAREER_LABELS[band],
                    count, "명", null, "career-" + group));
        }
    }

    private static ReportBundle.Metric metric(String id, UUID stageId, String label, double value, String unit,
            String key, String group) {
        return new ReportBundle.Metric(id, stageId, label, value, unit, key, group);
    }

    private static double round(double value) {
        return Math.round(value * 10) / 10.0;
    }

    private static ReportBundle.Stage stage(StageInfo stage) {
        return new ReportBundle.Stage(stage.id(), stage.name(), stage.type(), stage.confirmedAt());
    }

    /** 값 key 앞부분. 전형 종류 이름이고, 범위에 같은 종류가 앞에 또 있으면 번호를 붙인다 (interview2). */
    static String prefix(List<StageInfo> scope, StageInfo stage) {
        List<UUID> same = scope.stream().filter(other -> other.type() == stage.type()).map(StageInfo::id)
                .toList();
        int order = same.indexOf(stage.id()) + 1;
        String name = stage.type().name().toLowerCase(Locale.ROOT);
        return order <= 1 ? name : name + order;
    }

    /** 묶음 값을 모은다. 같은 지원자 · key는 한 번만 넣는다. */
    private static final class Facts {

        private final List<ReportBundle.Fact> list = new ArrayList<>();
        private final Map<String, String> labels = new HashMap<>();

        void number(String number, UUID stageId, String key, String label, BigDecimal value, Double max) {
            if (value != null) {
                add(number, stageId, key, label, value.doubleValue(), max);
            }
        }

        void verdict(String number, UUID stageId, String key, String label, String value) {
            add(number, stageId, key, label, value, null);
        }

        private void add(String number, UUID stageId, String key, String label, Object value, Double max) {
            labels.put(key, label);
            list.add(new ReportBundle.Fact(number + "-" + key, number, stageId, key, label, value, max));
        }

        boolean has(String key) {
            return labels.containsKey(key);
        }

        /** prefix로 시작하는 key. 넣은 순서다. */
        List<String> keys(String prefix) {
            return list.stream().map(ReportBundle.Fact::key).filter(key -> key.startsWith(prefix)).distinct().toList();
        }

        String label(String key) {
            return labels.getOrDefault(key, key);
        }

        Optional<Double> average(String key) {
            List<Double> values = list.stream().filter(fact -> fact.key().equals(key) && fact.value() instanceof Double)
                    .map(fact -> (Double) fact.value()).toList();
            return values.isEmpty() ? Optional.empty()
                    : Optional.of(round(values.stream().mapToDouble(Double::doubleValue).average()
                            .orElse(0)));
        }

        Optional<Double> average(String key, List<String> numbers) {
            List<Double> values = list.stream()
                    .filter(fact -> fact.key().equals(key) && numbers.contains(fact.applicant())
                            && fact.value() instanceof Double)
                    .map(fact -> (Double) fact.value()).toList();
            return values.isEmpty() ? Optional.empty()
                    : Optional.of(round(values.stream().mapToDouble(Double::doubleValue).average()
                            .orElse(0)));
        }
    }
}
