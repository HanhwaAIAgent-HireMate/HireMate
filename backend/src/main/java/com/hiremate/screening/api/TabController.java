package com.hiremate.screening.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageTabService;
import com.hiremate.screening.StageTabView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 전형 화면의 탭과 탭의 선택 지원자 편집 API. 탭은 같은 기업 담당자가 함께 쓴다. */
@RestController
@RequestMapping("/api/stages/{stageId}/tabs")
public class TabController {

    private final StageTabService tabs;
    private final ScreeningService screening;

    public TabController(StageTabService tabs, ScreeningService screening) {
        this.tabs = tabs;
        this.screening = screening;
    }

    @GetMapping
    public List<StageTabView> tabs(AuthenticatedMember member, @PathVariable UUID stageId) {
        return tabs.tabs(member.companyId(), stageId, member);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public StageTabView createTab(AuthenticatedMember member, @PathVariable UUID stageId) {
        return tabs.create(member.companyId(), stageId, member);
    }

    @PatchMapping("/{tabId}")
    public StageTabView renameTab(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId,
            @Valid @RequestBody RenameRequest request) {
        tabs.requireAccess(member, stageId, tabId);
        return tabs.rename(member.companyId(), stageId, tabId, request.name());
    }

    @DeleteMapping("/{tabId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteTab(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId) {
        tabs.requireAccess(member, stageId, tabId);
        tabs.delete(member.companyId(), stageId, tabId);
    }

    @GetMapping("/{tabId}/selection")
    public CandidatePage selection(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId) {
        tabs.requireAccess(member, stageId, tabId);
        return screening.selection(member.companyId(), stageId, tabId);
    }

    @PostMapping("/{tabId}/selection/add")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void add(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId,
            @Valid @RequestBody Targets request) {
        tabs.requireAccess(member, stageId, tabId);
        screening.add(member.companyId(), stageId, tabId, request.applicationIds());
    }

    @PostMapping("/{tabId}/selection/remove")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void remove(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId,
            @Valid @RequestBody Targets request) {
        tabs.requireAccess(member, stageId, tabId);
        screening.remove(member.companyId(), stageId, tabId, request.applicationIds());
    }

    @PostMapping("/{tabId}/selection/clear")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clear(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId) {
        tabs.requireAccess(member, stageId, tabId);
        screening.clear(member.companyId(), stageId, tabId);
    }

    public record RenameRequest(@NotBlank @Size(max = 30) String name) {
    }

    public record Targets(@NotEmpty @Size(max = 500) List<@NotNull UUID> applicationIds) {
    }
}
