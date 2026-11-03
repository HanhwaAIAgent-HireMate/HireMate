package com.hiremate.ai.application;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.CriterionMark;
import com.hiremate.global.ApiException;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateFilter;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.CandidateSort;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/**
 * 서류 전형 분포 리포트를 센다. 모델을 부르지 않으므로 목표 인원을 바꿀 때마다 다시 센다.
 *
 * <p>경계 기준은 팀과 정하기 전의 임시값이라 설정(hiremate.report.distribution)에 둔다.
 */
@Service
public class ReportDistributions {

    private static final int PAGE = 200;

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ReportAgent agent;
    private final int targetMultiplier;
    private final int maxMissingRequired;
    private final int deepSize;

    ReportDistributions(RecruitService recruits, ScreeningService screening, ApplicationService applications,
            PostingService postings, ReportAgent agent,
            @Value("${hiremate.report.distribution.target-multiplier:10}") int targetMultiplier,
            @Value("${hiremate.report.distribution.max-missing-required:1}") int maxMissingRequired,
            @Value("${hiremate.report.distribution.deep-size:5}") int deepSize) {
        this.recruits = recruits;
        this.screening = screening;
        this.applications = applications;
        this.postings = postings;
        this.agent = agent;
        this.targetMultiplier = targetMultiplier;
        this.maxMissingRequired = maxMissingRequired;
        this.deepSize = deepSize;
    }

    /**
     * 서류 전형의 분포.
     *
     * @param target 서류 통과 목표 인원. null이면 공고 채용 인원 × 배수다. 저장하지 않는다
     */
    public ReportDistribution build(UUID companyId, UUID stageId, Integer target, CandidateSort sort) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        if (stage.type() != StageType.DOCUMENT) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_DOCUMENT_STAGE",
                    "Distribution reports are for document stages.");
        }
        List<CandidateRow> rows = rows(companyId, stageId);
        Map<UUID, ApplicantInfo> infos = applications.applicants(companyId,
                rows.stream().map(CandidateRow::applicationId).toList()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, Function.identity()));
        rows = rows.stream().filter(row -> infos.containsKey(row.applicationId())).toList();
        ScreeningRubric rubric = postings.screeningRubric(companyId, recruitment.id());
        List<String> requiredIds = rubric.criteria().stream().filter(ScreeningService::required)
                .map(ScreeningRubric.Criterion::criterionId).toList();
        Map<String, String> texts = rubric.criteria().stream().collect(Collectors.toMap(
                ScreeningRubric.Criterion::criterionId, ScreeningRubric.Criterion::text, (a, b) -> a,
                LinkedHashMap::new));

        Integer headcount = postings.view(companyId, recruitment.id()).content().headcount();
        int hireCount = headcount != null ? headcount : rubric.hireCount();
        int defaultTarget = Math.max(1, hireCount * targetMultiplier);
        int goal = target != null && target > 0 ? target : defaultTarget;

        List<CandidateRow> analyzed = rows.stream().filter(row -> row.analysisStatus() == AnalysisStatus.DONE)
                .toList();
        Function<CandidateRow, Integer> key = row -> sort == CandidateSort.TALENT
                ? row.metCount() + row.talentCount()
                : row.metCount();
        // 전체 지원자 줄 순서를 지키되(같은 개수는 이름 순), 분석 전에 올린 지원자도 개수 자리에 둔다
        List<CandidateRow> above = rows.stream().filter(CandidateRow::aboveLine)
                .sorted(Comparator.comparing(key).reversed()).toList();

        ReportDistribution.Cut cut = cut(above, goal, key);
        List<ReportDistribution.Group> groups = new ArrayList<>();
        if (cut != null) {
            groups.add(new ReportDistribution.Group("selection-edge", "목표 인원에서 동점인 지원자",
                    "필수 조건 충족자 중 목표 %d명째와 충족 개수(%d개)가 같은 지원자예요. 개수로는 구분되지 않아요."
                            .formatted(goal, cut.value()),
                    people(above.stream().filter(row -> key.apply(row) == cut.value()).toList(), infos, texts)));
        }
        groups.add(new ReportDistribution.Group("below-line", "필수 조건을 조금 못 채운 지원자",
                "필수 조건 중 못 채웠거나 확인이 필요한 것이 %d개 이하인 지원자예요.".formatted(maxMissingRequired),
                people(analyzed.stream().filter(row -> !row.aboveLine() && !row.missingRequired().isEmpty()
                        && row.missingRequired().size() <= maxMissingRequired).toList(), infos, texts)));

        return new ReportDistribution(stageId, rows.size(), analyzed.size(), above.size(), goal, defaultTarget,
                hireCount, targetMultiplier, sort, required(rows, infos, requiredIds),
                criteria(rubric, requiredIds, analyzed, infos), counts(above, key), cut, groups, deepSize,
                careers(rows), (int) rows.stream().filter(row -> row.decision() == Decision.PASS).count());
    }

    /**
     * 분포 해설. Report Agent가 숫자를 읽고 먼저 볼 점을 쓴다. ai 서버를 부르지 못하면 빈 해설이라 화면은 숫자 요약만
     * 보여 준다 (분포 자체는 해설과 상관없이 보인다).
     */
    public DistributionNote note(ReportDistribution distribution) {
        try {
            return agent.explain(distribution.forAi());
        } catch (ApiException exception) {
            return DistributionNote.EMPTY;
        }
    }

    private List<CandidateRow> rows(UUID companyId, UUID stageId) {
        List<CandidateRow> rows = new ArrayList<>();
        for (int page = 0;; page++) {
            var result = screening.candidates(companyId, stageId, null, null, CandidateFilter.NONE, page, PAGE);
            rows.addAll(result.items());
            if (rows.size() >= result.total() || result.items().isEmpty()) {
                return rows;
            }
        }
    }

    /** 선 위는 개수가 많은 순으로 서 있다. 목표 인원번째와 개수가 같은 줄의 처음과 끝을 찾는다. */
    static ReportDistribution.Cut cut(List<CandidateRow> above, int goal, Function<CandidateRow, Integer> key) {
        if (above.size() <= goal) {
            return null;
        }
        int value = key.apply(above.get(goal - 1));
        int from = 0;
        while (key.apply(above.get(from)) != value) {
            from++;
        }
        int to = from;
        while (to + 1 < above.size() && key.apply(above.get(to + 1)) == value) {
            to++;
        }
        return new ReportDistribution.Cut(value, from + 1, to + 1, goal - from);
    }

    private static ReportDistribution.Required required(List<CandidateRow> rows, Map<UUID, ApplicantInfo> infos,
            List<String> requiredIds) {
        Map<CriterionMark, Long> judged = rows.stream().collect(Collectors.groupingBy(
                row -> ReportBundles.required(row, infos.get(row.applicationId())), Collectors.counting()));
        return new ReportDistribution.Required(judged.getOrDefault(CriterionMark.MET, 0L).intValue(),
                judged.getOrDefault(CriterionMark.NOT_MET, 0L).intValue(),
                judged.getOrDefault(CriterionMark.UNKNOWN, 0L).intValue(), requiredIds);
    }

    private static List<ReportDistribution.CriterionStat> criteria(ScreeningRubric rubric, List<String> requiredIds,
            List<CandidateRow> analyzed, Map<UUID, ApplicantInfo> infos) {
        return rubric.criteria().stream().map(criterion -> {
            Map<CriterionMark, Long> marks = analyzed.stream()
                    .map(row -> infos.get(row.applicationId()).criterionMarks().get(criterion.criterionId()))
                    .map(mark -> mark == null ? CriterionMark.UNKNOWN : mark)
                    .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()));
            return new ReportDistribution.CriterionStat(criterion.criterionId(), criterion.category(),
                    criterion.text(), requiredIds.contains(criterion.criterionId()),
                    marks.getOrDefault(CriterionMark.MET, 0L).intValue(),
                    marks.getOrDefault(CriterionMark.PARTIAL, 0L).intValue(),
                    marks.getOrDefault(CriterionMark.NOT_MET, 0L).intValue(),
                    marks.getOrDefault(CriterionMark.UNKNOWN, 0L).intValue());
        }).toList();
    }

    private static List<ReportDistribution.CountBucket> counts(List<CandidateRow> above,
            Function<CandidateRow, Integer> key) {
        return above.stream().collect(Collectors.groupingBy(key, Collectors.counting())).entrySet().stream()
                .sorted(Map.Entry.<Integer, Long>comparingByKey().reversed())
                .map(entry -> new ReportDistribution.CountBucket(entry.getKey(), entry.getValue().intValue()))
                .toList();
    }

    /** 확인 필요가 많은 순, 같으면 부분 충족이 많은 순. 그다음은 전체 지원자 줄 순서다. */
    private static List<ReportDistribution.Person> people(List<CandidateRow> rows, Map<UUID, ApplicantInfo> infos,
            Map<String, String> texts) {
        return rows.stream().map(row -> {
            Map<String, CriterionMark> marks = infos.get(row.applicationId()).criterionMarks();
            return new ReportDistribution.Person(row.applicationId(), row.name(), row.careerYears(), row.metCount(),
                    row.criterionTotal(), row.talentCount(), count(marks, CriterionMark.UNKNOWN),
                    count(marks, CriterionMark.PARTIAL),
                    row.missingRequired().stream().map(id -> texts.getOrDefault(id, id)).toList());
        }).sorted(Comparator.comparingInt(ReportDistribution.Person::unknownCount).reversed()
                .thenComparing(Comparator.comparingInt(ReportDistribution.Person::partialCount).reversed()))
                .toList();
    }

    private static int count(Map<String, CriterionMark> marks, CriterionMark mark) {
        return (int) marks.values().stream().filter(value -> Objects.equals(value, mark)).count();
    }

    private static List<ReportDistribution.CareerBand> careers(List<CandidateRow> rows) {
        List<ReportDistribution.CareerBand> bands = new ArrayList<>();
        for (int band = 0; band < ReportBundles.CAREER_BANDS.length; band++) {
            int low = ReportBundles.CAREER_BANDS[band][0];
            int high = ReportBundles.CAREER_BANDS[band][1];
            List<CandidateRow> inBand = rows.stream().filter(row -> row.careerYears() != null
                    && row.careerYears() >= low && row.careerYears() <= high).toList();
            bands.add(new ReportDistribution.CareerBand(ReportBundles.CAREER_LABELS[band], inBand.size(),
                    (int) inBand.stream().filter(CandidateRow::aboveLine).count()));
        }
        return bands;
    }
}
