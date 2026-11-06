package com.hiremate.screening;

import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageStatus;
import com.hiremate.screening.domain.StageCandidate;
import com.hiremate.screening.domain.StageCandidateRepository;
import com.hiremate.screening.domain.StageTab;
import com.hiremate.screening.domain.StageTabRepository;
import com.hiremate.screening.domain.TabSelection;
import com.hiremate.screening.domain.TabSelectionRepository;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
    private final StageCandidateRepository candidates;
    private final RecruitService recruits;
    private final ApplicationEventPublisher events;

    public StageTabService(StageTabRepository tabs, TabSelectionRepository selections,
            StageCandidateRepository candidates, RecruitService recruits, ApplicationEventPublisher events) {
        this.tabs = tabs;
        this.selections = selections;
        this.candidates = candidates;
        this.recruits = recruits;
        this.events = events;
    }

    /** 전형의 HR 공유 탭. 만든 순서다. 시작하지 않은 전형에는 탭이 없다. */
    @Transactional(readOnly = true)
    public List<StageTabView> tabs(UUID companyId, UUID stageId) {
        return views(companyId, stageId, null);
    }

    /**
     * 계정이 보는 탭: HR은 같은 기업이 함께 쓰는 탭, 면접관은 자기만 보는 탭. 면접관에게 아직 탭이 없으면 진행 중인
     * 전형에서 하나 만든다 (면접관 모드의 AI Chat).
     */
    @Transactional
    public List<StageTabView> tabs(UUID companyId, UUID stageId, AuthenticatedMember member) {
        UUID owner = owner(member);
        StageStatus status = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status();
        if (owner != null && scope(companyId, stageId, owner).isEmpty() && status == StageStatus.ACTIVE) {
            create(companyId, stageId, owner);
        }
        return views(companyId, stageId, owner);
    }

    private List<StageTabView> views(UUID companyId, UUID stageId, UUID owner) {
        recruits.getByStage(companyId, stageId);
        List<StageTab> found = scope(companyId, stageId, owner);
        Set<UUID> pending = pending(companyId, stageId);
        Map<UUID, Long> counts = selections.findByTabIdIn(found.stream().map(StageTab::getId).toList()).stream()
                .filter(selection -> pending.contains(selection.getApplicationId()))
                .collect(Collectors.groupingBy(TabSelection::getTabId, Collectors.counting()));
        return found.stream().map(tab -> view(tab, counts.getOrDefault(tab.getId(), 0L))).toList();
    }

    /** 전형의 HR 공유 탭과 탭마다의 선택 지원자. 만든 순서다. 결정한 지원자는 빼고, 탭 안은 선택한 순서다. */
    @Transactional(readOnly = true)
    public List<StageTabSelection> selections(UUID companyId, UUID stageId) {
        List<StageTab> found = scope(companyId, stageId, null);
        Set<UUID> pending = pending(companyId, stageId);
        Map<UUID, List<UUID>> picked = selections.findByTabIdIn(found.stream().map(StageTab::getId).toList()).stream()
                .filter(selection -> pending.contains(selection.getApplicationId()))
                .sorted(Comparator.comparing(TabSelection::getSelectedAt))
                .collect(Collectors.groupingBy(TabSelection::getTabId,
                        Collectors.mapping(TabSelection::getApplicationId, Collectors.toList())));
        return found.stream().map(tab -> new StageTabSelection(tab.getId(), tab.getName(),
                List.copyOf(picked.getOrDefault(tab.getId(), List.of())))).toList();
    }

    /** 빈 탭을 만든다. 이름은 "새 탭"이고, 번호는 남은 탭의 가장 큰 번호 다음이다. */
    @Transactional
    public StageTabView create(UUID companyId, UUID stageId) {
        return create(companyId, stageId, (UUID) null);
    }

    /** 계정의 탭을 만든다. 탭 수 제한(20개)은 HR 공유 탭과 면접관 각자의 탭을 따로 센다. */
    @Transactional
    public StageTabView create(UUID companyId, UUID stageId, AuthenticatedMember member) {
        return create(companyId, stageId, owner(member));
    }

    private StageTabView create(UUID companyId, UUID stageId, UUID owner) {
        requireActive(companyId, stageId);
        if (scope(companyId, stageId, owner).size() >= MAX_TABS) {
            throw new ApiException(HttpStatus.CONFLICT, "TAB_LIMIT", "A stage can have up to 20 tabs.");
        }
        // 번호는 전형 안에서 겹치지 않아야 해서 모든 탭에서 센다
        int number = tabs.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId).stream()
                .mapToInt(StageTab::getNumber).max().orElse(0) + 1;
        return view(tabs.save(new StageTab(companyId, stageId, number, owner)), 0);
    }

    /** 계정이 열 수 있는 탭인가: HR은 공유 탭, 면접관은 자기 탭. 아니면 다른 전형의 탭처럼 404다. */
    @Transactional(readOnly = true)
    public void requireAccess(AuthenticatedMember member, UUID stageId, UUID tabId) {
        StageTab tab = tab(member.companyId(), stageId, tabId);
        if (!Objects.equals(tab.getOwnerMemberId(), owner(member))) {
            throw new ApiException(HttpStatus.NOT_FOUND, "TAB_NOT_FOUND", "Tab not found in this stage.");
        }
    }

    /** 면접관이 자기만 보는 탭인가. 이 탭의 Chat은 선택 지원자를 바꾸지 않는다. */
    @Transactional(readOnly = true)
    public boolean personal(UUID companyId, UUID stageId, UUID tabId) {
        return tab(companyId, stageId, tabId).getOwnerMemberId() != null;
    }

    private List<StageTab> scope(UUID companyId, UUID stageId, UUID owner) {
        return tabs.findByStageIdAndCompanyIdOrderByNumber(stageId, companyId).stream()
                .filter(tab -> Objects.equals(tab.getOwnerMemberId(), owner)).toList();
    }

    private static UUID owner(AuthenticatedMember member) {
        return member.hr() ? null : member.memberId();
    }

    /** 담당자가 이름을 바꾼다. 그 뒤로는 자동 제목이 붙지 않는다. */
    @Transactional
    public StageTabView rename(UUID companyId, UUID stageId, UUID tabId, String name) {
        StageTab tab = tab(companyId, stageId, tabId);
        tab.rename(name.strip());
        return view(tab, count(companyId, stageId, tabId));
    }

    /** 탭과 그 탭의 선택 지원자를 지운다. 대화방은 {@link TabDeleted}를 받은 쪽이 지운다. */
    @Transactional
    public void delete(UUID companyId, UUID stageId, UUID tabId) {
        requireActive(companyId, stageId);
        StageTab tab = tab(companyId, stageId, tabId);
        if (scope(companyId, stageId, tab.getOwnerMemberId()).size() <= 1) {
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
        return new StageTabView(tab.getId(), tab.getName(), selectedCount);
    }
}
