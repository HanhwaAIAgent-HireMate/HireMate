package com.hiremate.posting.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.mail.MailPreview;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.posting.PublicPostingView;
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

    /** HR이 전형 절차를 직접 정한다. 게시 전에만 바꿀 수 있고, 이름이 같은 전형은 입력해 둔 안내를 이어 받는다. */
    @PutMapping("/api/recruitments/{recruitmentId}/posting/stages")
    public PostingView changeStages(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody StagesRequest request) {
        return postings.changeStages(member.companyId(), recruitmentId, request.toDrafts());
    }

    /** 본문 없이 부르면 수정안 전체를, fields가 있으면 그 칸만 적용한다. */
    @PostMapping("/api/recruitments/{recruitmentId}/posting/suggestion/apply")
    public PostingView applySuggestion(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody(required = false) SuggestionFieldsRequest request) {
        return postings.applySuggestion(member.companyId(), recruitmentId, SuggestionFieldsRequest.fields(request));
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

    /** 본문 없이 부르면 수정안 전체를, fields가 있으면 그 칸만 되돌린다. */
    @PostMapping("/api/recruitments/{recruitmentId}/posting/suggestion/discard")
    public PostingView discardSuggestion(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody(required = false) SuggestionFieldsRequest request) {
        return postings.discardSuggestion(member.companyId(), recruitmentId, SuggestionFieldsRequest.fields(request));
    }

    /** 지원자가 받을 접수 확인 메일의 모습. 지금 설정 › 안내 메일의 양식으로 만들고 지원자 값은 예시다. */
    @GetMapping("/api/recruitments/{recruitmentId}/posting/receipt/preview")
    public MailPreview receiptPreview(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return postings.receiptPreview(member.companyId(), recruitmentId);
    }
}
