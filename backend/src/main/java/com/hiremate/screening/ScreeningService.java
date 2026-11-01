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
import com.hiremate.global.JsonText;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.domain.SelectionSnapshot;
import com.hiremate.screening.domain.SelectionSnapshotRepository;
import com.hiremate.screening.domain.StageCandidate;
import com.hiremate.screening.domain.StageCandidateRepository;
import com.hiremate.screening.domain.StageRequirement;
import com.hiremate.screening.domain.StageRequirementRepository;
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
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.type.TypeReference;

/**
 * 공통 전형 화면 (FR-10 ~ FR-24). 지원자 상태를 바꾸는 유일한 모듈이다.
 * 선택 지원자는 탭마다 따로 두고, AI Chat의 선택 편집 명령도 이 서비스가 대상과 권한을 검증한 뒤 탭에 실행한다.
 * 결정한 지원자는 탭에 행이 남아도 선택 지원자에 보이지 않는다. 빼기 · 비우기 · 교체 · 되돌리기는 보이는 선택 지원자에만
 * 적용하므로, 결정을 되돌리면 그 지원자는 원래 탭에 AI 표시 그대로 돌아온다.
 */
@Service
public class ScreeningService {

    /** 점수 높은 순. 점수가 없으면 뒤에 선다. */
    private static final Comparator<BigDecimal> HIGH_FIRST = Comparator.nullsLast(Comparator.reverseOrder());

    /** 같은 충족 개수의 지원자는 이름 가나다순이다. */
    private static final Collator NAME_ORDER = Collator.getInstance(Locale.KOREAN);

    private final StageCandidateRepository candidates;
    private final SelectionSnapshotRepository snapshots;
    private final StageTabRepository tabRepository;
    private final TabSelectionRepository selections;
    private final StageTabService tabs;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ActivityService activity;
    private final StageRequirementRepository requirements;
    private final CompanyService companies;

    public ScreeningService(StageCandidateRepository candidates, SelectionSnapshotRepository snapshots,
            StageTabRepository tabRepository, TabSelectionRepository selections, StageTabService tabs,
            RecruitService recruits, ApplicationService applications, PostingService postings,
            ActivityService activity, StageRequirementRepository requirements, CompanyService companies) {
        this.candidates = candidates;
        this.snapshots = snapshots;
        this.tabRepository = tabRepository;
        this.selections = selections;
        this.tabs = tabs;
        this.recruits = recruits;
        this.applications = applications;
        this.postings = postings;
        this.activity = activity;
        this.requirements = requirements;
        this.companies = companies;
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
     * 전체 지원자 리스트. 서류 전형은 선 위(필수 조건 충족 · ↑로 올림) 지원자를 먼저, 그 안에서 sort 기준 충족 개수가 많은
     * 순으로 세우고 같으면 이름 순이다. 분석이 끝나지 않은 지원자는 선 아래 맨 뒤다. 평가 전형은 점수 높은 순이다.
     */
    @Transactional(readOnly = true)
    public CandidatePage candidates(UUID companyId, UUID stageId, UUID tabId, String query, CandidateSort sort,
            int page, int size) {
        StageContext context = context(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, TabSelection> selected = tabId == null ? Map.of() : visible(tabs.tab(companyId, stageId, tabId), all);
        List<CandidateRow> rows = rows(context, all, selected, sort);
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
        List<CandidateRow> rows = rows(context, all, selected, CandidateSort.BASIC).stream()
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

    /** 탭의 선택 지원자를 비운다. 되돌릴 수 있게 남긴다. */
    @Transactional
    public void clear(UUID companyId, UUID stageId, UUID tabId) {
        activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        Map<UUID, TabSelection> visible = visible(tab, candidates.findByStageIdAndCompanyId(stageId, companyId));
        snapshot(tab.getId(), visible);
        selections.deleteAll(visible.values());
    }

    /** 교체 · 좁히기 · 비우기 직전의 선택 지원자로 돌아간다. 그 사이 결정한 지원자는 돌아오지 않는다. */
    @Transactional
    public void restore(UUID companyId, UUID stageId, UUID tabId) {
        activeContext(companyId, stageId);
        StageTab tab = tabs.tab(companyId, stageId, tabId);
        SelectionSnapshot snapshot = snapshots.findById(tab.getId()).orElseThrow(() -> new ApiException(
                HttpStatus.CONFLICT, "NOTHING_TO_RESTORE", "There is no previous selection."));
        List<SnapshotEntry> previous = JsonText.read(snapshot.getEntries(),
                new TypeReference<List<SnapshotEntry>>() { });
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Set<UUID> pending = all.stream().filter(candidate -> candidate.getDecision() == Decision.PENDING)
                .map(StageCandidate::getApplicationId).collect(Collectors.toSet());
        selections.deleteAll(visible(tab, all).values());
        selections.flush();
        previous.stream().filter(entry -> pending.contains(entry.applicationId()))
                .forEach(entry -> selections.save(new TabSelection(tab.getId(), entry.applicationId(), entry.ai())));
        snapshots.delete(snapshot);
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
                snapshot(tab.getId(), visible);
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
        snapshots.deleteAllById(tabIds.stream().filter(snapshots::existsById).toList());
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

    private void snapshot(UUID tabId, Map<UUID, TabSelection> visible) {
        String entries = JsonText.write(visible.values().stream()
                .sorted(Comparator.comparing(TabSelection::getSelectedAt))
                .map(row -> new SnapshotEntry(row.getApplicationId(), row.isAi()))
                .toList());
        snapshots.findById(tabId).ifPresentOrElse(snapshot -> snapshot.replace(entries),
                () -> snapshots.save(new SelectionSnapshot(tabId, entries)));
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
            Map<UUID, TabSelection> selected, CandidateSort sort) {
        Map<UUID, ApplicantInfo> infos = infos(context);
        Lines lines = lines(context);
        Set<UUID> recommended = recommended(lines, infos);
        Comparator<CandidateRow> byTotal = Comparator
                .comparing(row -> totalKey(infos.get(row.applicationId())), HIGH_FIRST);
        Comparator<CandidateRow> order = switch (context.type()) {
            case DOCUMENT -> Comparator.comparing((CandidateRow row) -> !row.aboveLine())
                    .thenComparing(row -> row.analysisStatus() != AnalysisStatus.DONE)
                    .thenComparing(row -> sort == CandidateSort.TALENT ? row.metCount() + row.talentCount()
                            : row.metCount(), Comparator.reverseOrder())
                    .thenComparing(CandidateRow::name, NAME_ORDER);
            case ASSESSMENT -> Comparator.comparing(CandidateRow::score, HIGH_FIRST).thenComparing(byTotal);
            case INTERVIEW -> byTotal;
        };
        return all.stream()
                .map(candidate -> toRow(context.type(), candidate, infos.get(candidate.getApplicationId()),
                        recommended, selected.get(candidate.getApplicationId()), lines))
                .sorted(order.thenComparing(row -> infos.get(row.applicationId()).applicationNo()))
                .toList();
    }

    /**
     * 서류 전형의 선 위 지원자: 분석이 끝났고 필수 조건을 모두 충족한(MET) 지원자. 필수 조건이 없으면 분석이 끝난 지원자 모두다.
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
            return new Lines(false, List.of(), List.of(), List.of());
        }
        List<ScreeningRubric.Criterion> criteria = postings
                .screeningRubric(context.companyId(), context.recruitmentId()).criteria();
        return new Lines(true, criteria.stream().map(ScreeningRubric.Criterion::criterionId).toList(),
                requiredIds(context.stageId(), criteria),
                companies.factors(context.companyId()).stream().map(Talent::title).toList());
    }

    /** HR이 체크한 필수 조건. 체크한 적이 없으면 공고 기준에서 중요 표시한 자격요건이다. */
    private List<String> requiredIds(UUID stageId, List<ScreeningRubric.Criterion> criteria) {
        List<String> known = criteria.stream().map(ScreeningRubric.Criterion::criterionId).toList();
        return requirements.findById(stageId)
                .map(saved -> saved.criterionIds().stream().filter(known::contains).toList())
                .orElseGet(() -> criteria.stream()
                        .filter(criterion -> criterion.important()
                                && criterion.category() == ScreeningRubric.Category.QUALIFICATION)
                        .map(ScreeningRubric.Criterion::criterionId)
                        .toList());
    }

    /** 서류 전형의 필수 조건. */
    @Transactional(readOnly = true)
    public StageRequirements requirements(UUID companyId, UUID stageId) {
        return new StageRequirements(lines(context(companyId, stageId)).required());
    }

    /** 필수 조건을 바꾼다. 선 위 지원자가 바로 달라진다. 이미 선택 지원자에 있는 지원자는 그대로 둔다. */
    @Transactional
    public StageRequirements updateRequirements(UUID companyId, UUID stageId, Collection<String> criterionIds) {
        StageContext context = activeContext(companyId, stageId);
        if (context.type() != StageType.DOCUMENT) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_DOCUMENT_STAGE", "Only document stages have a line.");
        }
        List<String> chosen = lines(context).criteria().stream().filter(criterionIds::contains).toList();
        if (chosen.size() != new HashSet<>(criterionIds).size()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "Unknown criterion.");
        }
        requirements.findById(stageId).ifPresentOrElse(saved -> saved.replace(chosen),
                () -> requirements.save(new StageRequirement(stageId, companyId, chosen)));
        return new StageRequirements(chosen);
    }

    /** 총점 순 정렬 값. 보류면 확인 필요를 0점으로 계산한 점수이고, 그것도 없으면(서류를 읽지 못함) 0점이다. */
    private static BigDecimal totalKey(ApplicantInfo info) {
        return heldAsZero(info, info.documentScore() != null ? info.documentScore() : info.documentScoreLow());
    }

    private static BigDecimal heldAsZero(ApplicantInfo info, BigDecimal score) {
        return score == null && info.held() ? BigDecimal.ZERO : score;
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
                candidate.getScore(), info.analysisStatus(), document && info.held(),
                document ? info.shortfalls() : List.of(), document ? info.documentScore() : null,
                document ? info.documentScoreLow() : null,
                document ? info.qualificationScore() : null, document ? info.qualificationMax() : 0,
                document ? info.preferenceScore() : null, document ? info.preferenceMax() : 0, lines.met(info),
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

    private record SnapshotEntry(UUID applicationId, boolean ai) {
    }

    /** 서류 전형의 줄 세우기 기준. criteria는 평가 항목 ID, required는 필수 조건 ID, talents는 인재상 제목이다. */
    private record Lines(boolean document, List<String> criteria, List<String> required, List<String> talents) {

        int met(ApplicantInfo info) {
            return (int) criteria.stream().filter(id -> info.criterionMarks().get(id) == CriterionMark.MET).count();
        }

        int strong(ApplicantInfo info) {
            return (int) talents.stream().filter(info.highTalents()::contains).count();
        }

        List<String> missing(ApplicantInfo info) {
            return required.stream().filter(id -> info.criterionMarks().get(id) != CriterionMark.MET).toList();
        }
    }
}
