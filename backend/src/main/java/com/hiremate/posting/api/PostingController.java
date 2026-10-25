package com.hiremate.posting.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.posting.PublicPostingView;
import com.hiremate.posting.ScreeningCriteriaView;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 공고 작성 화면(PST-01) API. */
@RestController
public class PostingController {

    private final PostingService postings;

    public PostingController(PostingService postings) {
        this.postings = postings;
    }

    /** 새 채용. 기업 공고 Template으로 공고 초안을 만든다. */
    @PostMapping("/api/recruitments")
    @ResponseStatus(HttpStatus.CREATED)
    public PostingView create(AuthenticatedMember member) {
        return postings.createDraft(member.companyId());
    }

    @GetMapping("/api/recruitments/{recruitmentId}/posting")
    public PostingView get(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.view(member.companyId(), recruitmentId);
    }

    @PutMapping("/api/recruitments/{recruitmentId}/posting")
    public PostingView update(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PostingContentRequest request) {
        return postings.updateContent(member.companyId(), recruitmentId, request.toContent());
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/suggestion/apply")
    public PostingView applySuggestion(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.applySuggestion(member.companyId(), recruitmentId);
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/publish")
    public PostingView publish(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PublishRequest request) {
        return postings.publish(member.companyId(), recruitmentId, member.memberId(), request.openAt(),
                request.closeAt());
    }

    /** [지금 마감]. 접수를 마감하고 첫 전형을 시작한다. */
    @PostMapping("/api/recruitments/{recruitmentId}/posting/close")
    public PostingView close(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.close(member.companyId(), recruitmentId);
    }

    @GetMapping("/api/public/postings/{postingId}")
    public PublicPostingView publicPosting(@PathVariable UUID postingId) {
        return postings.publicView(postingId);
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/suggestion/discard")
    public PostingView discardSuggestion(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.discardSuggestion(member.companyId(), recruitmentId);
    }

    /** 접수 확인 메일. 게시 전에만 고칠 수 있다. */
    @PutMapping("/api/recruitments/{recruitmentId}/posting/receipt")
    public PostingView changeReceipt(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody ReceiptRequest request) {
        return postings.changeReceipt(member.companyId(), recruitmentId, request.toTemplate());
    }

    /** 서류 평가 기준과 선발 인원. 공고 작성 화면이 자격요건 · 우대사항 줄마다 기준을 보여 준다. */
    @GetMapping("/api/recruitments/{recruitmentId}/posting/criteria")
    public ScreeningCriteriaView screeningCriteria(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.screeningCriteria(member.companyId(), recruitmentId);
    }

    /** 서류 평가 기준과 선발 인원 저장. 게시 전에만 고칠 수 있다. */
    @PutMapping("/api/recruitments/{recruitmentId}/posting/criteria")
    public ScreeningCriteriaView changeScreeningCriteria(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody CriteriaRequest request) {
        return postings.changeScreeningCriteria(member.companyId(), recruitmentId, request.hireCount(),
                request.criteria().stream().map(CriteriaRequest.CriterionInput::toCriterion).toList());
    }
}
