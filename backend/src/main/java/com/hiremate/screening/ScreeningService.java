package com.hiremate.screening;

import com.hiremate.activity.ActivityService;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.CriterionMark;
import com.hiremate.company.CompanyService;
import com.hiremate.company.Talent;
import com.hiremate.global.ApiException;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.domain.StageCandidate;
import com.hiremate.screening.domain.StageCandidateRepository;
import com.hiremate.screening.domain.StageTab;
import com.hiremate.screening.domain.StageTabRepository;
import com.hiremate.screening.domain.TabSelection;
import com.hiremate.screening.domain.TabSelectionRepository;
import java.math.BigDecimal;
import java.text.Collator;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 공통 전형 화면 (FR-10 ~ FR-24). 지원자 상태를 바꾸는 유일한 모듈이다.
 * 선택 지원자는 탭마다 따로 두고, AI Chat의 선택 편집 명령도 이 서비스가 대상과 권한을 검증한 뒤 탭에 실행한다.
 * 결정한 지원자는 탭에 행이 남아도 선택 지원자에 보이지 않는다. 빼기 · 비우기 · 교체는 보이는 선택 지원자에만
 * 적용하므로, 결정을 되돌리면 그 지원자는 원래 탭에 AI 표시 그대로 돌아온다.
 */
@Service
public class ScreeningService {

    /** 점수 높은 순. 점수가 없으면 뒤에 선다. */
    private static final Comparator<BigDecimal> HIGH_FIRST = Comparator.nullsLast(Comparator.reverseOrder());

    /** 같은 충족 개수의 지원자는 이름 가나다순이다. */
    private static final Collator NAME_ORDER = Collator.getInstance(Locale.KOREAN);

    private final StageCandidateRepository candidates;
    private final StageTabRepository tabRepository;
    private final TabSelectionRepository selections;
    private final StageTabService tabs;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ActivityService activity;
    private final CompanyService companies;
    private final ApplicationEventPublisher events;

    public ScreeningService(StageCandidateRepository candidates, StageTabRepository tabRepository,
            TabSelectionRepository selections, StageTabService tabs, RecruitService recruits,
            ApplicationService applications, PostingService postings, ActivityService activity,
            CompanyService companies, ApplicationEventPublisher events) {
        this.candidates = candidates;
        this.tabRepository = tabRepository;
        this.selections = selections;
        this.tabs = tabs;
        this.recruits = recruits;
        this.applications = applications;
        this.postings = postings;
        this.activity = activity;
        this.companies = companies;
        this.events = events;
    }

    /** 전형을 시작하며 대상 지원자를 넣고 첫 탭을 만든다. 첫 전형은 지원자 전원, 이후 전형은 앞 전형 합격자다. */
    @Transactional
    public void startStage(UUID companyId, UUID stageId, Collection<UUID> applicationIds) {
        if (candidates.existsByStageId(stageId)) {
            return;
        }
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        candidates.saveAll(applicationIds.stream()
                .map(applicationId -> new StageCandidate(stageId, recruitment.id(), companyId, applicationId))
                .toList());
        if (!tabRepository.existsByStageId(stageId)) {
            tabRepository.save(new StageTab(companyId, stageId, 1));
        }
        events.publishEvent(new StageCandidatesStarted(companyId, stageId, List.copyOf(applicationIds)));
    }

    /** 전형 전체 지원자 ID. 면접처럼 공통 설정을 적용하는 업무 모듈이 사용한다. */
    @Transactional(readOnly = true)
    public List<UUID> applicationIds(UUID companyId, UUID stageId) {
        recruits.getByStage(companyId, stageId);
        return candidates.findByStageIdAndCompanyId(stageId, companyId).stream()
                .map(StageCandidate::getApplicationId).toList();
    }

    @Transactional(readOnly = true)
    public StageOverview overview(UUID companyId, UUID stageId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        Map<UUID, List<StageCandidate>> byStage = candidates
                .findByRecruitmentIdAndCompanyId(recruitment.id(), companyId).stream()
                .collect(Collectors.groupingBy(StageCandidate::getStageId));
        List<StageCandidate> current = byStage.getOrDefault(stageId, List.of());
        List<StageOverview.StageStep> steps = recruitment.stages().stream()
                .map(step -> new StageOverview.StageStep(step.id(), step.name(), step.type(), step.status(),
                        byStage.containsKey(step.id()) ? (long) byStage.get(step.id()).size() : null, step.icon()))
                .toList();
        return new StageOverview(stageId, stage.name(), stage.type(), stage.status(),
                recruitment.isLastStage(stageId), recruitment.id(), recruitment.title(), recruitment.status(),
                postings.view(companyId, recruitment.id()).postingId(),
                applications.count(companyId, recruitment.id()), steps, counts(current),
                current.stream().anyMatch(candidate -> candidate.getScore() != null), stage.confirmedAt(),
                stage.confirmedByName(), current.stream().filter(StageCandidate::isUndecidedAtConfirm).count());
    }

    /**
     * 전체 지원자 리스트. 서류 전형은 선 위(필수 자격요건 충족 · ↑로 올림) 지원자를 먼저, 그 안에서 자격요건 + 우대사항
     * 충족 개수에 상으로 판정한 인재상 개수를 더한 값이 많은 순으로 세우고 같으면 이름 순이다. 분석이 끝나지 않은 지원자는
     * 선 아래 맨 뒤다. 평가 전형은 점수 높은 순이다. filter에 맞지 않는 지원자는 빠진다.
     */
    @Transactional(readOnly = true)
    public CandidatePage candidates(UUID companyId, UUID stageId, UUID tabId, String query, CandidateFilter filter,
            int page, int size) {
        StageContext context = context(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, TabSelection> selected = tabId == null ? Map.of() : visible(tabs.tab(companyId, stageId, tabId), all);
        List<CandidateRow> rows = rows(context, all, selected, filter);
        if (query != null && !query.isBlank()) {
            String keyword = query.trim().toLowerCase(Locale.ROOT);
            Set<UUID> textMatches = new HashSet<>(
                    applications.searchDocuments(companyId, context.recruitmentId(), query.trim()));
            rows = rows.stream().filter(row -> matches(row, keyword) || textMatches.contains(row.applicationId()))
                    .toList();
        }
        int from = Math.min(Math.max(page, 0) * Math.clamp(size, 1, 200), rows.size());
        int to = Math.min(from + Math.clamp(size, 1, 200), rows.size());
        return new CandidatePage(rows.size(), rows.subList(from, to));
    }

    /** 탭의 선택 지원자. 넣은 순서이고, 결정한 지원자는 빠진다. */
    @Transactional(readOnly = true)
    public CandidatePage selection(UUID companyId, UUID stageId, UUID tabId) {
        StageContext context = context(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, TabSelection> selected = visible(tabs.tab(companyId, stageId, tabId), all);
        // 넣은 순서대로, 한 번에 넣었으면 리스트 순서대로 둔다
        List<CandidateRow> rows = rows(context, all, selected, CandidateFilter.NONE).stream()
                .filter(CandidateRow::selected)
                .sorted(Comparator.comparing(row -> selected.get(row.applicationId()).getSelectedAt()))
                .toList();
        return new CandidatePage(rows.size(), rows);
    }

    /** HR이 직접 넣는다. 테두리 없이 들어가고, 서류 전형의 기준 미달 지원자는 ↑로 올린 뒤에만 넣는다. */
    @Transactional
    public void add(UUID companyId, UUID stageId, UUID tabId, Collection<UUID> applicationIds) {
        add(companyId, stageId, tabId, applicationIds, false);
    }

    private void add(UUID companyId, UUID stageId, UUID tabId, Collection<UUID> applicationIds, boolean byAi) {
        StageContext context = activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        Map<UUID, TabSelection> rows = tabRows(tab);
        for (StageCandidate candidate : targets(companyId, stageId, applicationIds)) {
            requireSelectable(context, candidate);
            TabSelection row = rows.get(candidate.getApplicationId());
            if (row == null) {
                selections.save(new TabSelection(tab.getId(), candidate.getApplicationId(), byAi));
            } else if (byAi) {
                row.markAi(true);
            }
        }
    }

    /** Chat으로 넣는다. 이미 선택 지원자에 있던 지원자까지 테두리를 붙이고, 넣을 수 있는 조건은 직접 넣기와 같다. */
    @Transactional
    public void addByAi(UUID companyId, UUID stageId, UUID tabId, Collection<UUID> applicationIds) {
        add(companyId, stageId, tabId, applicationIds, true);
    }

    /** 빼기는 결정이 아니다. 뺀 지원자는 결정 전 상태 그대로 리스트에 남는다. */
    @Transactional
    public void remove(UUID companyId, UUID stageId, UUID tabId, Collection<UUID> applicationIds) {
        activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        Map<UUID, TabSelection> visible = visible(tab, candidates.findByStageIdAndCompanyId(stageId, companyId));
        targets(companyId, stageId, applicationIds).stream()
                .map(candidate -> visible.get(candidate.getApplicationId()))
                .filter(row -> row != null)
                .forEach(selections::delete);
    }

    /** 탭의 선택 지원자를 비운다. */
    @Transactional
    public void clear(UUID companyId, UUID stageId, UUID tabId) {
        activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        Map<UUID, TabSelection> visible = visible(tab, candidates.findByStageIdAndCompanyId(stageId, companyId));
        selections.deleteAll(visible.values());
    }

    /**
     * AI 탐색 결과를 선택 지원자에 반영한다. AI는 결정하지 않은 지원자만, 서류 전형에서는 기준을 넘은 지원자만 고를 수 있다.
     * AI가 고른 지원자는 이미 선택 지원자에 있었어도 테두리를 붙인다.
     * 조건에 맞지 않는 대상은 빼고 반영한 지원자 ID를 돌려준다. 추가는 신규 대상만, 교체와 좁히기는 최종 대상을 돌려준다.
     */
    @Transactional
    public List<UUID> applyAiSelection(UUID companyId, UUID stageId, UUID tabId, SelectionMode mode,
            Collection<UUID> applicationIds) {
        StageContext context = activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, StageCandidate> byApplication = all.stream()
                .collect(Collectors.toMap(StageCandidate::getApplicationId, Function.identity()));
        Map<UUID, TabSelection> rows = tabRows(tab);
        Map<UUID, TabSelection> visible = visible(tab, all);
        Set<UUID> recommended = recommended(context, infos(context));
        List<StageCandidate> chosen = applicationIds.stream().distinct()
                .filter(byApplication::containsKey)
                .map(byApplication::get)
                .filter(candidate -> candidate.getDecision() == Decision.PENDING)
                .filter(candidate -> aboveLine(context.type(), candidate, recommended))
                .filter(candidate -> mode != SelectionMode.NARROW || visible.containsKey(candidate.getApplicationId()))
                .toList();
        if (chosen.isEmpty()) {
            return List.of();
        }
        List<UUID> applied = chosen.stream()
                .map(StageCandidate::getApplicationId)
                .filter(applicationId -> mode != SelectionMode.ADD || !visible.containsKey(applicationId))
                .toList();
        if (mode != SelectionMode.ADD) {
            Set<UUID> retained = chosen.stream().map(StageCandidate::getApplicationId).collect(Collectors.toSet());
            if (!visible.keySet().equals(retained)) {
                visible.values().stream().filter(row -> !retained.contains(row.getApplicationId()))
                        .forEach(selections::delete);
            }
        }
        for (StageCandidate candidate : chosen) {
            TabSelection row = rows.get(candidate.getApplicationId());
            if (row == null) {
                selections.save(new TabSelection(tab.getId(), candidate.getApplicationId(), true));
            } else {
                row.markAi(true);
            }
        }
        return applied;
    }

    /** 회색(기준 미달) 지원자를 선 위로 올린다. 선택 지원자에 넣거나 합격 처리하지 않는다. */
    @Transactional
    public void promote(UUID companyId, UUID stageId, UUID applicationId) {
        StageContext context = activeContext(companyId, stageId);
        if (context.type() != StageType.DOCUMENT) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_DOCUMENT_STAGE", "Only document stages have a line.");
        }
        candidate(companyId, stageId, applicationId).promote();
    }

    /** 체크한 지원자를 한 번에 결정한다. 확인 창 없이 반영되고, 결정한 지원자는 선택 지원자에서 빠진다. */
    @Transactional
    public void decide(UUID companyId, UUID stageId, UUID memberId, Collection<UUID> applicationIds,
            Decision decision) {
        if (decision == Decision.PENDING) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "Choose pass or fail.");
        }
        activeContext(companyId, stageId);
        for (StageCandidate candidate : targets(companyId, stageId, applicationIds)) {
            candidate.decide(decision, memberId);
            activity.record(companyId, memberId, "DECIDE", "APPLICATION", candidate.getApplicationId(),
                    decision.name());
        }
    }

    /**
     * 방금 한 결정을 되돌린다. 지원자는 원래 있던 탭들에 같은 순서와 AI 표시로 다시 보이고,
     * 되돌리기를 누른 탭에 없던 지원자는 그 탭에 들어온다.
     */
    @Transactional
    public void revert(UUID companyId, UUID stageId, UUID tabId, UUID memberId, Collection<UUID> applicationIds) {
        activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        Map<UUID, TabSelection> rows = tabRows(tab);
        for (StageCandidate candidate : targets(companyId, stageId, applicationIds)) {
            if (candidate.getDecision() != Decision.PENDING) {
                candidate.revert();
                if (!rows.containsKey(candidate.getApplicationId())) {
                    selections.save(new TabSelection(tab.getId(), candidate.getApplicationId(), false));
                }
                activity.record(companyId, memberId, "REVERT_DECISION", "APPLICATION", candidate.getApplicationId(),
                        null);
            }
        }
    }

    @Transactional(readOnly = true)
    public CandidateDetail detail(UUID companyId, UUID stageId, UUID applicationId) {
        StageContext context = context(companyId, stageId);
        StageCandidate candidate = candidate(companyId, stageId, applicationId);
        ApplicantDetail applicant = applications.detail(companyId, applicationId);
        Lines lines = lines(context);
        Set<UUID> recommended = recommended(lines, infos(context));
        // 카드는 탭을 모르므로 선택 표시를 붙이지 않는다
        return new CandidateDetail(toRow(context.type(), candidate, applicant.info(), recommended, null, lines),
                applicant.info().email(),
                applicant.phone(), applicant.info().submittedAt(), applicant.certificates(), applicant.documents(),
                candidate.getMemo());
    }

    @Transactional
    public void changeMemo(UUID companyId, UUID stageId, UUID applicationId, String memo) {
        candidate(companyId, stageId, applicationId).changeMemo(memo);
    }

    /** 평가 결과의 총점. 평가 전형 리스트 오른쪽에 붙고 점수 높은 순 정렬에 쓴다. */
    @Transactional
    public void recordScore(UUID companyId, UUID stageId, UUID applicationId, BigDecimal score) {
        candidate(companyId, stageId, applicationId).changeScore(score);
    }

    /** 전형 결과 확정. 합격자만 다음 전형 대상이 되고, 불합격과 미결정은 모두 불합격으로 확정된다 (FR-24). */
    @Transactional
    public StageOverview.DecisionCounts confirm(UUID companyId, UUID stageId, UUID memberId, String memberName) {
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        StageOverview.DecisionCounts before = counts(all);
        recruits.confirmStage(companyId, stageId, memberId, memberName);
        all.forEach(StageCandidate::confirm);
        // 끝난 전형의 탭에는 이름과 대화만 남는다
        List<UUID> tabIds = tabRepository.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId).stream()
                .map(StageTab::getId).toList();
        selections.deleteAll(selections.findByTabIdIn(tabIds));
        activity.record(companyId, memberId, "CONFIRM_STAGE", "STAGE", stageId,
                "pass=" + before.pass() + ", fail=" + (before.fail() + before.pending()));
        return before;
    }

    /** 확정한 결과. 전형을 확정하기 전에는 409다. */
    @Transactional(readOnly = true)
    public StageResults results(UUID companyId, UUID stageId) {
        StageContext context = context(companyId, stageId);
        if (context.status() == StageStatus.ACTIVE || context.status() == StageStatus.PENDING) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_CONFIRMED", "Confirm the stage results first.");
        }
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        return new StageResults(stageId,
                all.stream().filter(candidate -> candidate.getFinalResult() == Decision.PASS)
                        .map(StageCandidate::getApplicationId).toList(),
                all.stream().filter(candidate -> candidate.getFinalResult() == Decision.FAIL)
                        .map(StageCandidate::getApplicationId).toList(),
                all.stream().filter(StageCandidate::isUndecidedAtConfirm).count());
    }

    /** 전형을 종료하고 합격자로 다음 전형을 시작한다. 마지막 전형이면 채용이 끝나고 빈 값이다. */
    @Transactional
    public Optional<UUID> finish(UUID companyId, UUID stageId, UUID memberId) {
        StageResults results = results(companyId, stageId);
        Optional<StageInfo> next = recruits.finishStage(companyId, stageId);
        next.ifPresent(stage -> startStage(companyId, stage.id(), results.passed()));
        activity.record(companyId, memberId, "FINISH_STAGE", "STAGE", stageId, null);
        return next.map(StageInfo::id);
    }

    /** 채용의 전형별 대상 · 결정 인원. 대시보드와 리포트가 쓴다. */
    @Transactional(readOnly = true)
    public Map<UUID, StageOverview.DecisionCounts> stageCounts(UUID companyId, UUID recruitmentId) {
        return candidates.findByRecruitmentIdAndCompanyId(recruitmentId, companyId).stream()
                .collect(Collectors.groupingBy(StageCandidate::getStageId)).entrySet().stream()
                .collect(Collectors.toMap(Map.Entry::getKey, entry -> counts(entry.getValue())));
    }

    /** 지원자의 이전 전형 메모와 결과. 다음 전형 화면에서 함께 본다. */
    @Transactional(readOnly = true)
    public List<StageCandidateView> history(UUID companyId, UUID applicationId) {
        List<StageCandidate> found = candidates.findByApplicationIdAndCompanyId(applicationId, companyId);
        if (found.isEmpty()) {
            return List.of();
        }
        RecruitmentInfo recruitment = recruits.get(companyId, found.getFirst().getRecruitmentId());
        return recruitment.stages().stream()
                .flatMap(stage -> found.stream().filter(candidate -> candidate.getStageId().equals(stage.id()))
                        .map(candidate -> new StageCandidateView(stage.id(), stage.name(), stage.type(),
                                candidate.getDecision(), candidate.getFinalResult(), candidate.getScore(),
                                candidate.getMemo())))
                .toList();
    }

    private StageContext context(UUID companyId, UUID stageId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        return new StageContext(companyId, recruitment.id(), stageId, stage.type(), stage.status());
    }

    private StageContext activeContext(UUID companyId, UUID stageId) {
        StageContext context = context(companyId, stageId);
        if (context.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The stage is not in progress.");
        }
        return context;
    }

    private void requireSelectable(StageContext context, StageCandidate candidate) {
        if (candidate.getDecision() != Decision.PENDING) {
            throw new ApiException(HttpStatus.CONFLICT, "ALREADY_DECIDED", "Decided applicants are not selectable.");
        }
        Set<UUID> recommended = context.type() == StageType.DOCUMENT
                ? recommended(context, infos(context))
                : Set.of();
        if (!aboveLine(context.type(), candidate, recommended)) {
            throw new ApiException(HttpStatus.CONFLICT, "BELOW_LINE", "Move the applicant above the line first.");
        }
    }

    private List<StageCandidate> targets(UUID companyId, UUID stageId, Collection<UUID> applicationIds) {
        List<StageCandidate> found = candidates.findByStageIdAndCompanyIdAndApplicationIdIn(stageId, companyId,
                applicationIds);
        if (found.size() != new HashSet<>(applicationIds).size()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "CANDIDATE_NOT_FOUND", "Applicant not found in this stage.");
        }
        return found;
    }

    private StageCandidate candidate(UUID companyId, UUID stageId, UUID applicationId) {
        return candidates.findByStageIdAndCompanyIdAndApplicationId(stageId, companyId, applicationId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "CANDIDATE_NOT_FOUND", "Applicant not found."));
    }

    /** 탭의 선택 행 전부. 결정한 지원자의 숨은 행도 있다. */
    private Map<UUID, TabSelection> tabRows(StageTab tab) {
        return selections.findByTabIdOrderBySelectedAt(tab.getId()).stream()
                .collect(Collectors.toMap(TabSelection::getApplicationId, Function.identity(),
                        (first, second) -> first, LinkedHashMap::new));
    }

    /** 탭의 선택 지원자: 결정하지 않은 지원자의 행만. */
    private Map<UUID, TabSelection> visible(StageTab tab, List<StageCandidate> all) {
        Set<UUID> pending = all.stream().filter(candidate -> candidate.getDecision() == Decision.PENDING)
                .map(StageCandidate::getApplicationId).collect(Collectors.toSet());
        Map<UUID, TabSelection> visible = new LinkedHashMap<>(tabRows(tab));
        visible.keySet().retainAll(pending);
        return visible;
    }

    private Map<UUID, ApplicantInfo> infos(StageContext context) {
        return applications.applicants(context.companyId(), context.recruitmentId()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, Function.identity()));
    }

    private List<CandidateRow> rows(StageContext context, List<StageCandidate> all,
            Map<UUID, TabSelection> selected, CandidateFilter filter) {
        Map<UUID, ApplicantInfo> infos = infos(context);
        Lines lines = lines(context);
        Set<UUID> recommended = recommended(lines, infos);
        // 서류는 점수를 매기지 않는다. 평가 점수가 같거나 점수가 없는 전형은 이름 순이다
        Comparator<CandidateRow> byName = Comparator.comparing(CandidateRow::name, NAME_ORDER);
        Comparator<CandidateRow> order = switch (context.type()) {
            case DOCUMENT -> Comparator.comparing((CandidateRow row) -> !row.aboveLine())
                    .thenComparing(row -> row.analysisStatus() != AnalysisStatus.DONE)
                    .thenComparing(row -> row.metCount() + row.talentCount(), Comparator.reverseOrder())
                    .thenComparing(CandidateRow::name, NAME_ORDER);
            case ASSESSMENT -> Comparator.comparing(CandidateRow::score, HIGH_FIRST).thenComparing(byName);
            case INTERVIEW -> byName;
        };
        return all.stream()
                .filter(candidate -> filter.decisions().isEmpty() || filter.decisions().contains(effective(candidate)))
                .filter(candidate -> lines.passes(infos.get(candidate.getApplicationId()), filter))
                .map(candidate -> toRow(context.type(), candidate, infos.get(candidate.getApplicationId()),
                        recommended, selected.get(candidate.getApplicationId()), lines))
                .sorted(order.thenComparing(row -> infos.get(row.applicationId()).applicationNo()))
                .toList();
    }

    /**
     * 서류 전형의 선 위 지원자: 분석이 끝났고 필수 자격요건을 모두 충족한(MET) 지원자. 필수 자격요건이 없으면 분석이 끝난
     * 지원자 모두다.
     * 서류 전형이 아니면 비어 있다.
     */
    private Set<UUID> recommended(StageContext context, Map<UUID, ApplicantInfo> infos) {
        return recommended(lines(context), infos);
    }

    private static Set<UUID> recommended(Lines lines, Map<UUID, ApplicantInfo> infos) {
        if (!lines.document()) {
            return Set.of();
        }
        return infos.values().stream()
                .filter(info -> info.analysisStatus() == AnalysisStatus.DONE && lines.missing(info).isEmpty())
                .map(ApplicantInfo::applicationId)
                .collect(Collectors.toSet());
    }

    /** 필수 조건 · 평가 항목 · 인재상. 서류 전형이 아니면 모두 비어 있다. */
    private Lines lines(StageContext context) {
        if (context.type() != StageType.DOCUMENT) {
            return new Lines(false, List.of(), List.of(), Set.of(), List.of());
        }
        List<ScreeningRubric.Criterion> criteria = postings
                .screeningRubric(context.companyId(), context.recruitmentId()).criteria();
        return new Lines(true, criteria.stream().map(ScreeningRubric.Criterion::criterionId).toList(),
                criteria.stream().filter(ScreeningService::required).map(ScreeningRubric.Criterion::criterionId)
                        .toList(),
                criteria.stream()
                        .filter(criterion -> criterion.criterionType() == ScreeningRubric.CriterionType.CONDITION)
                        .map(ScreeningRubric.Criterion::criterionId).collect(Collectors.toSet()),
                companies.factors(context.companyId()).stream().map(Talent::title).toList());
    }

    /** 필수 자격요건: 공고 평가 기준에서 중요 표시한 자격요건. 우대사항은 필수가 아니다. 표 보기 · 거르기의 '필수'와 같다. */
    public static boolean required(ScreeningRubric.Criterion criterion) {
        return criterion.important() && criterion.category() == ScreeningRubric.Category.QUALIFICATION;
    }

    private static boolean aboveLine(StageType type, StageCandidate candidate, Set<UUID> recommended) {
        return type != StageType.DOCUMENT || candidate.isPromoted()
                || recommended.contains(candidate.getApplicationId());
    }

    private static boolean matches(CandidateRow row, String keyword) {
        String career = row.careerYears() == null ? ""
                : row.careerYears() == 0 ? "신입" : "경력 " + row.careerYears() + "년";
        return row.name().toLowerCase(Locale.ROOT).contains(keyword) || career.contains(keyword)
                || row.lastCompany() != null && row.lastCompany().toLowerCase(Locale.ROOT).contains(keyword);
    }

    /** selection은 고른 탭에서 보이는 선택 행이다. 없으면 선택 지원자가 아니다. */
    private static CandidateRow toRow(StageType type, StageCandidate candidate, ApplicantInfo info,
            Set<UUID> recommended, TabSelection selection, Lines lines) {
        boolean document = type == StageType.DOCUMENT;
        return new CandidateRow(candidate.getApplicationId(), info.name(), info.careerYears(), info.lastCompany(),
                candidate.getFinalResult() != null ? candidate.getFinalResult() : candidate.getDecision(),
                selection != null, selection != null && selection.isAi(), aboveLine(type, candidate, recommended),
                candidate.getScore(), info.analysisStatus(), document ? info.shortfalls() : List.of(), lines.met(info),
                lines.criteria().size(), lines.strong(info), lines.talents().size(),
                document ? lines.missing(info) : List.of());
    }

    private static StageOverview.DecisionCounts counts(List<StageCandidate> all) {
        long pass = all.stream().filter(candidate -> effective(candidate) == Decision.PASS).count();
        long fail = all.stream().filter(candidate -> effective(candidate) == Decision.FAIL).count();
        return new StageOverview.DecisionCounts(all.size() - pass - fail, pass, fail, all.size());
    }

    private static Decision effective(StageCandidate candidate) {
        return candidate.getFinalResult() != null ? candidate.getFinalResult() : candidate.getDecision();
    }

    private record StageContext(UUID companyId, UUID recruitmentId, UUID stageId, StageType type,
            StageStatus status) {
    }

    /**
     * 서류 전형의 줄 세우기 기준. criteria는 평가 항목 ID, required는 필수 조건 ID, conditions는 조건형(O · X) 항목 ID,
     * talents는 인재상 제목이다.
     */
    private record Lines(boolean document, List<String> criteria, List<String> required, Set<String> conditions,
            List<String> talents) {

        int met(ApplicantInfo info) {
            return (int) criteria.stream().filter(id -> info.criterionMarks().get(id) == CriterionMark.MET).count();
        }

        int strong(ApplicantInfo info) {
            return (int) talents.stream().filter(info.highTalents()::contains).count();
        }

        List<String> missing(ApplicantInfo info) {
            return required.stream().filter(id -> info.criterionMarks().get(id) != CriterionMark.MET).toList();
        }

        /**
         * 거르기에서 고른 평가 항목과 인재상(T-1, T-2 …)이 모두 표 보기 표기로 O 또는 중 이상인가.
         * 조건형은 충족(O)만, 경험형은 충족 · 부분 충족(상 · 중)을, 인재상은 상 · 중을 남긴다.
         */
        boolean passes(ApplicantInfo info, CandidateFilter filter) {
            return filter.criteria().stream().allMatch(id -> fits(id, info.criterionMarks().get(id)))
                    && filter.talents().stream().allMatch(id -> talent(id)
                            .filter(title -> info.highTalents().contains(title) || info.midTalents().contains(title))
                            .isPresent());
        }

        private boolean fits(String id, CriterionMark mark) {
            return mark == CriterionMark.MET || mark == CriterionMark.PARTIAL && !conditions.contains(id);
        }

        /** 표 보기 열 ID(T-1부터)의 인재상 제목. 없는 ID면 비어 있다. */
        private Optional<String> talent(String id) {
            if (!id.matches("T-\\d{1,3}")) {
                return Optional.empty();
            }
            int index = Integer.parseInt(id.substring(2)) - 1;
            return index >= 0 && index < talents.size() ? Optional.of(talents.get(index)) : Optional.empty();
        }
    }
}
