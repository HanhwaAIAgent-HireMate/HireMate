package com.hiremate.ai.api;

import com.hiremate.ai.application.PosterAgent;
import com.hiremate.company.CompanyService;
import com.hiremate.company.PosterBrand;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PosterProposal;
import com.hiremate.posting.PosterTurn;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.recruit.RecruitmentStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 추천은 저장하지 않는다. 기업과 공고 범위는 인증된 업무 데이터로 고정한다. */
@RestController
public class PosterAiController {
    private final PostingService postings;
    private final CompanyService companies;
    private final PosterAgent agent;
    private final Validator validator;

    public PosterAiController(PostingService postings, CompanyService companies, PosterAgent agent,
            Validator validator) {
        this.postings = postings;
        this.companies = companies;
        this.agent = agent;
        this.validator = validator;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/ai-requests")
    public PosterProposal design(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PosterAiRequest request) {
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        PosterBrand brand = companies.posterBrand(member.companyId());
        PosterDesign current = request.design() == null ? posting.poster() : request.design();
        UUID logo = current == null ? null : current.logoFileId();
        UUID savedLogo = posting.poster() == null ? null : posting.poster().logoFileId();
        if (logo != null && !logo.equals(savedLogo) && !logo.equals(brand.logoFileId())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_POSTER_LOGO", "등록한 기업 로고만 사용할 수 있어요.");
        }
        PosterContext context = new PosterContext(companies.profile(member.companyId()), posting.content(),
                current, brand.logoFileId() == null ? null : brand.color(), request.history(),
                posting.stages().stream().map(PostingView.PostingStage::name).toList(), request.sectionNames());
        PosterProposal proposal = agent.design(context, request.message());
        if (!validator.validate(proposal).isEmpty()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_POSTER_PROPOSAL", "디자인 수정안을 확인하지 못했어요.");
        }
        if (proposal.recommendations().stream().anyMatch(item ->
                !context.stageNames().containsAll(item.design().stageIcons().keySet()))) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_POSTER_PROPOSAL", "전형 아이콘 수정안을 확인하지 못했어요.");
        }
        // AI가 만든 파일 ID는 신뢰하지 않고 현재 공고 로고를 보존한다.
        return new PosterProposal(proposal.reply(), proposal.recommendations().stream().map(item -> {
            PosterDesign design = item.design();
            return new PosterProposal.Recommendation(new PosterDesign(design.template(), design.mood(),
                    design.color(), design.decoration(), design.enabled(), design.showLogo() && logo != null, logo,
                    design.backgroundStyle(), design.stageIcons(), design.readableSections()),
                    item.reason());
        }).toList());
    }

    public record PosterAiRequest(@NotBlank @Size(max = 1000) String message,
            @Valid @Schema(nullable = true) PosterDesign design,
            @Size(max = 12) List<@NotNull @Valid PosterTurn> history,
            @Size(max = 12) List<@NotBlank @Size(max = 50) String> sectionNames) {
        public PosterAiRequest {
            history = history == null ? List.of() : List.copyOf(history);
            sectionNames = sectionNames == null ? List.of() : List.copyOf(sectionNames);
        }
    }
}
