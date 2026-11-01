package com.hiremate.screening;

import com.hiremate.global.ApiException;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageStatus;
import com.hiremate.screening.domain.SelectionSnapshotRepository;
import com.hiremate.screening.domain.StageCandidate;
import com.hiremate.screening.domain.StageCandidateRepository;
import com.hiremate.screening.domain.StageTab;
import com.hiremate.screening.domain.StageTabRepository;
import com.hiremate.screening.domain.TabSelection;
import com.hiremate.screening.domain.TabSelectionRepository;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 전형 화면의 탭: 선택 지원자와 AI Chat 대화방의 묶음. 같은 기업 담당자가 함께 쓰고, 전형이 끝나도 남는다.
 * 진행 중인 전형에서만 탭을 만들고 지운다. 이름은 언제든 바꿀 수 있다.
 */
@Service
public class StageTabService {

    static final int MAX_TABS = 20;
    static final int MAX_NAME = 30;

    private final StageTabRepository tabs;
    private final TabSelectionRepository selections;
    private final SelectionSnapshotRepository snapshots;
    private final StageCandidateRepository candidates;
    private final RecruitService recruits;
    private final ApplicationEventPublisher events;

    public StageTabService(StageTabRepository tabs, TabSelectionRepository selections,
            SelectionSnapshotRepository snapshots, StageCandidateRepository candidates, RecruitService recruits,
            ApplicationEventPublisher events) {
        this.tabs = tabs;
        this.selections = selections;
        this.snapshots = snapshots;
        this.candidates = candidates;
        this.recruits = recruits;
        this.events = events;
    }

    /** 전형의 탭. 만든 순서다. 시작하지 않은 전형에는 탭이 없다. */
    @Transactional(readOnly = true)
    public List<StageTabView> tabs(UUID companyId, UUID stageId) {
        recruits.getByStage(companyId, stageId);
        List<StageTab> found = tabs.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId);
        Set<UUID> pending = pending(companyId, stageId);
        Map<UUID, Long> counts = selections.findByTabIdIn(found.stream().map(StageTab::getId).toList()).stream()
                .filter(selection -> pending.contains(selection.getApplicationId()))
                .collect(Collectors.groupingBy(TabSelection::getTabId, Collectors.counting()));
        return found.stream().map(tab -> view(tab, counts.getOrDefault(tab.getId(), 0L))).toList();
    }

    /** 빈 탭을 만든다. 이름은 "새 탭"이고, 번호는 남은 탭의 가장 큰 번호 다음이다. */
    @Transactional
    public StageTabView create(UUID companyId, UUID stageId) {
        requireActive(companyId, stageId);
        List<StageTab> found = tabs.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId);
        if (found.size() >= MAX_TABS) {
            throw new ApiException(HttpStatus.CONFLICT, "TAB_LIMIT", "A stage can have up to 20 tabs.");
        }
        int number = found.stream().mapToInt(StageTab::getNumber).max().orElse(0) + 1;
        return view(tabs.save(new StageTab(companyId, stageId, number)), 0);
    }

    /** 담당자가 이름을 바꾼다. 그 뒤로는 자동 제목이 붙지 않는다. */
    @Transactional
    public StageTabView rename(UUID companyId, UUID stageId, UUID tabId, String name) {
        StageTab tab = tab(companyId, stageId, tabId);
        tab.rename(name.strip());
        return view(tab, count(companyId, stageId, tabId));
    }

    /** 탭과 그 탭의 선택 지원자 · 되돌리기를 지운다. 대화방은 {@link TabDeleted}를 받은 쪽이 지운다. */
    @Transactional
    public void delete(UUID companyId, UUID stageId, UUID tabId) {
        requireActive(companyId, stageId);
        StageTab tab = tab(companyId, stageId, tabId);
        if (tabs.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId).size() <= 1) {
            throw new ApiException(HttpStatus.CONFLICT, "LAST_TAB", "A stage keeps at least one tab.");
        }
        tabs.delete(tab);
        events.publishEvent(new TabDeleted(companyId, stageId, tabId));
    }

    /** 첫 대화 뒤의 자동 제목. 아직 자동 제목을 기다리는 탭만 바꾸고, 바꾸지 않았으면 빈 값이다. */
    @Transactional
    public Optional<StageTabView> autoName(UUID companyId, UUID stageId, UUID tabId, String name) {
        String title = name.strip();
        if (title.length() > MAX_NAME) {
            title = title.substring(0, MAX_NAME).strip();
        }
        StageTab tab = tab(companyId, stageId, tabId);
        if (title.isEmpty() || !tab.autoName(title)) {
            return Optional.empty();
        }
        return Optional.of(view(tab, count(companyId, stageId, tabId)));
    }

    /** 아직 자동 제목을 기다리는 탭인가. */
    @Transactional(readOnly = true)
    public boolean autoNamed(UUID companyId, UUID stageId, UUID tabId) {
        return tab(companyId, stageId, tabId).isAutoNamed();
    }

    StageTab tab(UUID companyId, UUID stageId, UUID tabId) {
        return tabs.findByIdAndStageIdAndCompanyId(tabId, stageId, companyId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "TAB_NOT_FOUND", "Tab not found in this stage."));
    }

    private void requireActive(UUID companyId, UUID stageId) {
        StageStatus status = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status();
        if (status != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The stage is not in progress.");
        }
    }

    private long count(UUID companyId, UUID stageId, UUID tabId) {
        Set<UUID> pending = pending(companyId, stageId);
        return selections.findByTabIdOrderBySelectedAt(tabId).stream()
                .filter(selection -> pending.contains(selection.getApplicationId())).count();
    }

    /** 결정하지 않은 지원자. 탭의 선택 지원자에는 이 지원자만 보인다. */
    private Set<UUID> pending(UUID companyId, UUID stageId) {
        return candidates.findByStageIdAndCompanyId(stageId, companyId).stream()
                .filter(candidate -> candidate.getDecision() == Decision.PENDING)
                .map(StageCandidate::getApplicationId).collect(Collectors.toSet());
    }

    private StageTabView view(StageTab tab, long selectedCount) {
        return new StageTabView(tab.getId(), tab.getName(), selectedCount, snapshots.existsById(tab.getId()));
    }
}
