package com.hiremate.screening.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.screening.CandidateDetail;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageOverview;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 공통 전형 화면 (Generic Stage Page) API. */
@RestController
@RequestMapping("/api/stages/{stageId}")
public class StageController {

    private final ScreeningService screening;

    public StageController(ScreeningService screening) {
        this.screening = screening;
    }

    @GetMapping
    public StageOverview overview(AuthenticatedMember member, @PathVariable UUID stageId) {
        return screening.overview(member.companyId(), stageId);
    }

    @GetMapping("/candidates")
    public CandidatePage candidates(AuthenticatedMember member, @PathVariable UUID stageId,
            @RequestParam(required = false) String query, @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "30") int size) {
        return screening.candidates(member.companyId(), stageId, query, page, size);
    }

    @GetMapping("/selection")
    public CandidatePage selection(AuthenticatedMember member, @PathVariable UUID stageId) {
        return screening.selection(member.companyId(), stageId);
    }

    @PostMapping("/selection/add")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void add(AuthenticatedMember member, @PathVariable UUID stageId, @Valid @RequestBody Targets request) {
        screening.add(member.companyId(), stageId, request.applicationIds());
    }

    @PostMapping("/selection/remove")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void remove(AuthenticatedMember member, @PathVariable UUID stageId, @Valid @RequestBody Targets request) {
        screening.remove(member.companyId(), stageId, request.applicationIds());
    }

    @PostMapping("/selection/clear")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clear(AuthenticatedMember member, @PathVariable UUID stageId) {
        screening.clear(member.companyId(), stageId);
    }

    @PostMapping("/selection/restore")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void restore(AuthenticatedMember member, @PathVariable UUID stageId) {
        screening.restore(member.companyId(), stageId);
    }

    @PostMapping("/candidates/{applicationId}/promote")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void promote(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID applicationId) {
        screening.promote(member.companyId(), stageId, applicationId);
    }

    @PostMapping("/decisions")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void decide(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody DecisionRequest request) {
        screening.decide(member.companyId(), stageId, member.memberId(), request.applicationIds(),
                request.decision());
    }

    @PostMapping("/decisions/revert")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void revert(AuthenticatedMember member, @PathVariable UUID stageId, @Valid @RequestBody Targets request) {
        screening.revert(member.companyId(), stageId, member.memberId(), request.applicationIds());
    }

    @GetMapping("/candidates/{applicationId}")
    public CandidateDetail detail(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return screening.detail(member.companyId(), stageId, applicationId);
    }

    @PutMapping("/candidates/{applicationId}/memo")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void memo(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID applicationId,
            @Valid @RequestBody MemoRequest request) {
        screening.changeMemo(member.companyId(), stageId, applicationId, request.memo());
    }

    /** 전형 결과 확정. 확정 직전 인원을 돌려준다. */
    @PostMapping("/confirm")
    public StageOverview.DecisionCounts confirm(AuthenticatedMember member, @PathVariable UUID stageId) {
        return screening.confirm(member.companyId(), stageId, member.memberId());
    }

    /** 전형 종료. 다음 전형이 있으면 그 ID를, 채용이 끝났으면 null을 돌려준다. */
    @PostMapping("/finish")
    public FinishResponse finish(AuthenticatedMember member, @PathVariable UUID stageId) {
        return new FinishResponse(screening.finish(member.companyId(), stageId, member.memberId()).orElse(null));
    }

    public record Targets(@NotEmpty @Size(max = 500) List<@NotNull UUID> applicationIds) {
    }

    public record DecisionRequest(@NotEmpty @Size(max = 500) List<@NotNull UUID> applicationIds,
            @NotNull Decision decision) {
    }

    public record MemoRequest(@NotNull @Size(max = 5000) String memo) {
    }

    public record FinishResponse(@Schema(nullable = true) UUID nextStageId) {
    }
}
