package com.hiremate.screening.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.screening.CandidateDetail;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.CandidateSort;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageCandidateView;
import com.hiremate.screening.StageOverview;
import com.hiremate.screening.StageRequirements;
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

    /** 전체 지원자. tabId를 주면 그 탭의 선택 표시와 AI 테두리를 붙인다. */
    @GetMapping("/candidates")
    public CandidatePage candidates(AuthenticatedMember member, @PathVariable UUID stageId,
            @RequestParam(required = false) UUID tabId, @RequestParam(required = false) String query,
            @RequestParam(defaultValue = "BASIC") CandidateSort sort,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "30") int size) {
        return screening.candidates(member.companyId(), stageId, tabId, query, sort, page, size);
    }

    /** 서류 전형의 필수 조건. 모두 충족한 지원자만 선 위(AI 단계)에 오른다. */
    @GetMapping("/requirements")
    public StageRequirements requirements(AuthenticatedMember member, @PathVariable UUID stageId) {
        return screening.requirements(member.companyId(), stageId);
    }

    @PutMapping("/requirements")
    public StageRequirements updateRequirements(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody RequirementsRequest request) {
        return screening.updateRequirements(member.companyId(), stageId, request.criterionIds());
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

    /** 결정 되돌리기. 되돌리기를 누른 탭에 없던 지원자는 그 탭에 넣는다. */
    @PostMapping("/decisions/revert")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void revert(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody RevertRequest request) {
        screening.revert(member.companyId(), stageId, request.tabId(), member.memberId(), request.applicationIds());
    }

    @GetMapping("/candidates/{applicationId}")
    public CandidateDetail detail(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return screening.detail(member.companyId(), stageId, applicationId);
    }

    /** 지원자의 전형별 결과 · 점수 · 메모 (지원자 카드의 전형 결과 탭). */
    @GetMapping("/candidates/{applicationId}/history")
    public List<StageCandidateView> history(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        screening.detail(member.companyId(), stageId, applicationId);
        return screening.history(member.companyId(), applicationId);
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
        return screening.confirm(member.companyId(), stageId, member.memberId(), member.name());
    }

    public record RevertRequest(@NotEmpty @Size(max = 500) List<@NotNull UUID> applicationIds,
            @NotNull UUID tabId) {
    }

    public record DecisionRequest(@NotEmpty @Size(max = 500) List<@NotNull UUID> applicationIds,
            @NotNull Decision decision) {
    }

    public record MemoRequest(@NotNull @Size(max = 5000) String memo) {
    }

    /** 필수로 체크한 평가 항목 ID. 비우면 필수 조건이 없다. */
    public record RequirementsRequest(@NotNull @Size(max = 100) List<@NotNull String> criterionIds) {
    }
}
