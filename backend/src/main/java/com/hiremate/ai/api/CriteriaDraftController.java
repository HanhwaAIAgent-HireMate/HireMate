package com.hiremate.ai.api;

import com.hiremate.ai.application.CriteriaDraftService;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.ScreeningRubric;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 공고 작성 화면의 서류 평가 기준 AI 초안. 초안은 화면의 입력 칸만 채우고 HR이 저장해야 기준이 된다. */
@RestController
public class CriteriaDraftController {

    private final CriteriaDraftService service;

    public CriteriaDraftController(CriteriaDraftService service) {
        this.service = service;
    }

    /** 자격요건 · 우대사항 한 항목의 유형과 판정 기준 초안. */
    @PostMapping("/api/recruitments/{recruitmentId}/posting/criteria/draft")
    public CriteriaDraftService.CriterionDraftAnswer draftCriterion(AuthenticatedMember member,
            @PathVariable UUID recruitmentId, @Valid @RequestBody CriterionDraftRequest request) {
        return service.draft(member.companyId(), recruitmentId, request.category(), request.text());
    }

    /** 목록마다 '중요'로 추천할 항목. */
    @PostMapping("/api/recruitments/{recruitmentId}/posting/criteria/important")
    public CriteriaDraftService.ImportantAnswer recommendImportant(AuthenticatedMember member,
            @PathVariable UUID recruitmentId) {
        return service.important(member.companyId(), recruitmentId);
    }

    public record CriterionDraftRequest(@NotNull ScreeningRubric.Category category,
            @NotBlank @Size(max = 300) String text) {
    }
}
