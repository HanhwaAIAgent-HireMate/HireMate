package com.hiremate.screening;

import com.hiremate.activity.ActivityService;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.global.JsonText;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.domain.SelectionSnapshot;
import com.hiremate.screening.domain.SelectionSnapshotRepository;
import com.hiremate.screening.domain.StageCandidate;
import com.hiremate.screening.domain.StageCandidateRepository;
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashSet;
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
 * AI Chat의 선택 편집 명령도 이 서비스가 대상과 권한을 검증한 뒤 실행한다.
 */
@Service
public class ScreeningService {

    private final StageCandidateRepository candidates;
    private final SelectionSnapshotRepository snapshots;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ActivityService activity;

    public ScreeningService(StageCandidateRepository candidates, SelectionSnapshotRepository snapshots,
            RecruitService recruits, ApplicationService applications, PostingService postings,
            ActivityService activity) {
        this.candidates = candidates;
        this.snapshots = snapshots;
        this.recruits = recruits;
        this.applications = applications;
        this.postings = postings;
        this.activity = activity;
    }

    /** 전형을 시작하며 대상 지원자를 넣는다. 첫 전형은 지원자 전원, 이후 전형은 앞 전형 합격자다. */
    @Transactional
    public void startStage(UUID companyId, UUID stageId, Collection<UUID> applicationIds) {
        if (candidates.existsByStageId(stageId)) {
            return;
        }
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        candidates.saveAll(applicationIds.stream()
                .map(applicationId -> new StageCandidate(stageId, recruitment.id(), companyId, applicationId))
                .toList());
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
                        byStage.containsKey(step.id()) ? (long) byStage.get(step.id()).size() : null))
                .toList();
        return new StageOverview(stageId, stage.name(), stage.type(), stage.status(),
                recruitment.isLastStage(stageId), recruitment.id(), recruitment.title(), recruitment.status(),
                postings.view(companyId, recruitment.id()).postingId(),
                applications.count(companyId, recruitment.id()), steps, counts(current),
                current.stream().filter(StageCandidate::isSelected).count(), snapshots.existsById(stageId),
                current.stream().anyMatch(candidate -> candidate.getScore() != null), stage.confirmedAt(),
                stage.confirmedByName(), current.stream().filter(StageCandidate::isUndecidedAtConfirm).count());
    }

    /**
     * 전체 지원자 리스트. 서류 전형은 AI 기준을 넘은(또는 올린) 지원자를 서류 점수 높은 순으로 먼저, 평가 전형은 점수 높은 순이다.
     */
    @Transactional(readOnly = true)
    public CandidatePage candidates(UUID companyId, UUID stageId, String query, int page, int size) {
        StageContext context = context(companyId, stageId);
        List<CandidateRow> rows = rows(context, candidates.findByStageIdAndCompanyId(stageId, companyId));
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

    /** 선택 지원자. 넣은 순서다. */
    @Transactional(readOnly = true)
    public CandidatePage selection(UUID companyId, UUID stageId) {
        StageContext context = context(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Map<UUID, StageCandidate> byApplication = all.stream()
                .collect(Collectors.toMap(StageCandidate::getApplicationId, Function.identity()));
        // 넣은 순서대로, 한 번에 넣었으면 리스트 순서대로 둔다
        List<CandidateRow> listed = rows(context, all);
        List<CandidateRow> selected = listed.stream()
                .filter(CandidateRow::selected)
                .sorted(Comparator.comparing(row -> byApplication.get(row.applicationId()).getSelectedAt()))
                .toList();
        return new CandidatePage(selected.size(), selected);
    }

    /** HR이 직접 넣는다. 테두리 없이 들어가고, 서류 전형의 기준 미달 지원자는 ↑로 올린 뒤에만 넣는다. */
    @Transactional
    public void add(UUID companyId, UUID stageId, Collection<UUID> applicationIds) {
        StageContext context = activeContext(companyId, stageId);
        for (StageCandidate candidate : targets(companyId, stageId, applicationIds)) {
            requireSelectable(context, candidate);
            candidate.select(false);
        }
    }

    /** 빼기는 결정이 아니다. 뺀 지원자는 결정 전 상태 그대로 리스트에 남는다. */
    @Transactional
    public void remove(UUID companyId, UUID stageId, Collection<UUID> applicationIds) {
        activeContext(companyId, stageId);
        targets(companyId, stageId, applicationIds).forEach(StageCandidate::unselect);
    }

    @Transactional
    public void clear(UUID companyId, UUID stageId) {
        activeContext(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        snapshot(stageId, all);
        all.forEach(StageCandidate::unselect);
    }

    /** 교체 · 좁히기 · 비우기 직전의 선택 지원자로 돌아간다. */
    @Transactional
    public void restore(UUID companyId, UUID stageId) {
        activeContext(companyId, stageId);
        SelectionSnapshot snapshot = snapshots.findById(stageId).orElseThrow(() -> new ApiException(
                HttpStatus.CONFLICT, "NOTHING_TO_RESTORE", "There is no previous selection."));
        Map<UUID, Boolean> previous = JsonText.read(snapshot.getEntries(), new TypeReference<List<SnapshotEntry>>() { })
                .stream()
                .collect(Collectors.toMap(SnapshotEntry::applicationId, SnapshotEntry::ai));
        for (StageCandidate candidate : candidates.findByStageIdAndCompanyId(stageId, companyId)) {
            if (previous.containsKey(candidate.getApplicationId()) && candidate.getDecision() == Decision.PENDING) {
                candidate.select(previous.get(candidate.getApplicationId()));
            } else {
                candidate.unselect();
            }
        }
        snapshots.delete(snapshot);
    }

    /**
     * AI 탐색 결과를 선택 지원자에 반영한다. AI는 결정하지 않은 지원자만, 서류 전형에서는 기준을 넘은 지원자만 고를 수 있다.
     * 조건에 맞지 않는 대상은 빼고 반영한 지원자 ID를 돌려준다.
     */
    @Transactional
    public List<UUID> applyAiSelection(UUID companyId, UUID stageId, SelectionMode mode,
            Collection<UUID> applicationIds) {
        StageContext context = activeContext(companyId, stageId);
        List<StageCandidate> all = candidates.findByStageIdAndCompanyId(stageId, companyId);
        Set<UUID> requested = new HashSet<>(applicationIds);
        Map<UUID, ApplicantInfo> infos = infos(context);
        List<StageCandidate> chosen = all.stream()
                .filter(candidate -> requested.contains(candidate.getApplicationId()))
                .filter(candidate -> candidate.getDecision() == Decision.PENDING)
                .filter(candidate -> aboveLine(context.type(), candidate, infos.get(candidate.getApplicationId())))
                .filter(candidate -> mode != SelectionMode.NARROW || candidate.isSelected())
                .toList();
        if (mode != SelectionMode.ADD) {
            snapshot(stageId, all);
            all.forEach(StageCandidate::unselect);
        }
        chosen.forEach(candidate -> candidate.select(true));
        return chosen.stream().map(StageCandidate::getApplicationId).toList();
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

    /** 방금 한 결정을 되돌린다. 카드가 선택 지원자로 돌아온다. */
    @Transactional
    public void revert(UUID companyId, UUID stageId, UUID memberId, Collection<UUID> applicationIds) {
        activeContext(companyId, stageId);
        for (StageCandidate candidate : targets(companyId, stageId, applicationIds)) {
            if (candidate.getDecision() != Decision.PENDING) {
                candidate.revert();
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
        return new CandidateDetail(toRow(context.type(), candidate, applicant.info()), applicant.info().email(),
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
        snapshots.deleteById(stageId);
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
        ApplicantInfo info = applications.applicants(context.companyId(), List.of(candidate.getApplicationId()))
                .getFirst();
        if (!aboveLine(context.type(), candidate, info)) {
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

    private void snapshot(UUID stageId, List<StageCandidate> all) {
        String entries = JsonText.write(all.stream().filter(StageCandidate::isSelected)
                .sorted(Comparator.comparing(StageCandidate::getSelectedAt))
                .map(candidate -> new SnapshotEntry(candidate.getApplicationId(), candidate.isAiSelected()))
                .toList());
        snapshots.findById(stageId).ifPresentOrElse(snapshot -> snapshot.replace(entries),
                () -> snapshots.save(new SelectionSnapshot(stageId, entries)));
    }

    private Map<UUID, ApplicantInfo> infos(StageContext context) {
        return applications.applicants(context.companyId(), context.recruitmentId()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, Function.identity()));
    }

    private List<CandidateRow> rows(StageContext context, List<StageCandidate> all) {
        Map<UUID, ApplicantInfo> infos = infos(context);
        Comparator<CandidateRow> byDocumentScore = Comparator.comparing(
                row -> infos.get(row.applicationId()).documentScore(),
                Comparator.nullsLast(Comparator.reverseOrder()));
        Comparator<CandidateRow> order = switch (context.type()) {
            case DOCUMENT -> Comparator.comparing(CandidateRow::aboveLine).reversed().thenComparing(byDocumentScore);
            case ASSESSMENT -> Comparator
                    .comparing(CandidateRow::score, Comparator.nullsLast(Comparator.reverseOrder()))
                    .thenComparing(byDocumentScore);
            case INTERVIEW -> byDocumentScore;
        };
        return all.stream()
                .map(candidate -> toRow(context.type(), candidate, infos.get(candidate.getApplicationId())))
                .sorted(order.thenComparing(row -> infos.get(row.applicationId()).applicationNo()))
                .toList();
    }

    private static boolean aboveLine(StageType type, StageCandidate candidate, ApplicantInfo info) {
        return type != StageType.DOCUMENT || candidate.isPromoted() || info != null && info.passed();
    }

    private static boolean matches(CandidateRow row, String keyword) {
        String career = row.careerYears() == null ? ""
                : row.careerYears() == 0 ? "신입" : "경력 " + row.careerYears() + "년";
        return row.name().toLowerCase(Locale.ROOT).contains(keyword) || career.contains(keyword)
                || row.lastCompany() != null && row.lastCompany().toLowerCase(Locale.ROOT).contains(keyword);
    }

    private static CandidateRow toRow(StageType type, StageCandidate candidate, ApplicantInfo info) {
        return new CandidateRow(candidate.getApplicationId(), info.name(), info.careerYears(), info.lastCompany(),
                candidate.getFinalResult() != null ? candidate.getFinalResult() : candidate.getDecision(),
                candidate.isSelected(), candidate.isAiMarked(), aboveLine(type, candidate, info),
                candidate.getScore(), info.analysisStatus());
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
}
