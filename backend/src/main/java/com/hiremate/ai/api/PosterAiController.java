package com.hiremate.ai.api;

import com.hiremate.ai.application.PosterAgent;
import com.hiremate.company.CanvaConnectionService;
import com.hiremate.company.CanvaConnectionService.CanvaTemplate;
import com.hiremate.company.CompanyService;
import com.hiremate.company.PosterBrand;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PosterProposal;
import com.hiremate.posting.PosterTemplateSearch;
import com.hiremate.posting.PosterTurn;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.posting.TemplatedLibrary;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageIcon;
import com.hiremate.recruit.StageType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;
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
    private final CanvaConnectionService canva;
    private final TemplatedLibrary templates;
    private final PosterTemplateSearch templateSearch;

    public PosterAiController(PostingService postings, CompanyService companies, PosterAgent agent,
            Validator validator, CanvaConnectionService canva, TemplatedLibrary templates,
            PosterTemplateSearch templateSearch) {
        this.postings = postings;
        this.companies = companies;
        this.agent = agent;
        this.validator = validator;
        this.canva = canva;
        this.templates = templates;
        this.templateSearch = templateSearch;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/ai-requests")
    public PosterProposal design(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PosterAiRequest request, HttpSession session) {
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
                posting.stages().stream().map(PostingView.PostingStage::name).toList(), request.sectionNames(),
                canva.status(member, session).connected(), posting.stages().stream().collect(Collectors.toMap(
                        PostingView.PostingStage::name, stage -> displayedIcon(stage, current))));
        PosterProposal proposal = agent.design(context, request.message());
        if (!validator.validate(proposal).isEmpty()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_POSTER_PROPOSAL", "디자인 수정안을 확인하지 못했어요.");
        }
        if (proposal.externalQuery() != null) {
            List<PosterProposal.FreeTemplate> candidates = List.of();
            List<CanvaConnectionService.CanvaDesign> canvaCandidates = List.of();
            String unavailable = "";
            try {
                candidates = templates.search(proposal.externalQuery());
            } catch (ApiException exception) {
                unavailable = " Templated에 연결하지 못했어요.";
            }
            if (context.canvaConnected()) {
                try {
                    canvaCandidates = canva.search(member, session,
                            proposal.canvaQuery() == null ? proposal.externalQuery() : proposal.canvaQuery());
                } catch (ApiException exception) {
                    unavailable += " Canva에 연결하지 못했어요.";
                }
            }
            var combined = templateSearch.combine(candidates, canvaCandidates);
            int count = combined.templates().size() + combined.designs().size();
            return new PosterProposal((count == 0
                    ? "요청에 맞고 공고로 변환할 수 있는 외부 테마가 없어요. 다른 분위기로 요청해 주세요."
                    : "Templated와 연결된 Canva 디자인에서 중복을 제외한 " + count
                            + "개를 찾았어요. 미리보기를 확인하고 선택해 주세요.") + unavailable
                            + (context.canvaConnected() ? "" : " Canva는 계정 연결 후 함께 검색해요."),
                    List.of(), combined.templates(), null, null, combined.designs());
        }
        if (proposal.canvaQuery() != null) {
            var designs = canva.search(member, session, proposal.canvaQuery());
            return new PosterProposal(designs.isEmpty()
                    ? "Canva 계정에서 일치하는 디자인을 찾지 못했어요. Canva에 저장한 디자인 이름으로 요청해 주세요."
                    : "연결한 Canva 계정에서 중복을 제외한 디자인 " + designs.size()
                            + "개를 찾았어요. 미리보기를 확인하고 선택해 주세요.",
                    List.of(), List.of(), null, null, designs);
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
                    design.backgroundStyle(), design.stageIcons(), design.readableSections(), design.canvasJson(),
                    design.tagline()),
                    item.reason());
        }).toList(), proposal.templates(), proposal.selectedTemplateId());
    }

    private static StageIcon displayedIcon(PostingView.PostingStage stage, PosterDesign design) {
        StageIcon icon = design == null ? StageIcon.AUTO
                : design.stageIcons().getOrDefault(stage.name(), StageIcon.AUTO);
        if (icon != StageIcon.AUTO) {
            return icon;
        }
        String name = stage.name().replace(" ", "");
        if (name.contains("검진")) {
            return StageIcon.HEALTH;
        }
        if (name.contains("코딩")) {
            return StageIcon.CODE;
        }
        if (stage.type() == StageType.INTERVIEW) {
            if (name.contains("2차") || name.contains("최종")) {
                return StageIcon.USERS;
            }
            return name.contains("실무") ? StageIcon.CHAIR : StageIcon.MESSAGES;
        }
        return stage.type() == StageType.DOCUMENT ? StageIcon.FILE_TEXT : StageIcon.CLIPBOARD_CHECK;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/canva-import")
    public CanvaImport importCanva(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody CanvaImportRequest request, HttpSession session) {
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        CanvaTemplate template = canva.importTemplate(member, session, request.designId());
        return new CanvaImport(template, agent.mapCanva(template.regions()));
    }

    public record CanvaImportRequest(
            @NotBlank @jakarta.validation.constraints.Pattern(regexp = "D[A-Za-z0-9_-]{5,79}") String designId) {
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/template-layout")
    public PosterAgent.TemplateLayout templateLayout(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody TemplateLayoutRequest request) {
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        return agent.templateLayout(request.regions().stream().map(region -> new PosterAgent.LayoutRegion(
                region.id(), region.text(), region.left(), region.top(), region.width(), region.height(),
                region.kind())).toList());
    }

    public record TemplateLayoutRequest(@Size(min = 2, max = 150) List<@Valid TemplateLayoutRegion> regions) {
    }

    public record TemplateLayoutRegion(@NotBlank @Size(max = 100) String id,
            @NotNull @Size(max = 10000) String text,
            @jakarta.validation.constraints.DecimalMin("0") @jakarta.validation.constraints.DecimalMax("5000")
            double left,
            @jakarta.validation.constraints.DecimalMin("0") @jakarta.validation.constraints.DecimalMax("5000")
            double top,
            @jakarta.validation.constraints.DecimalMin("0") @jakarta.validation.constraints.DecimalMax("5000")
            double width,
            @jakarta.validation.constraints.DecimalMin("0") @jakarta.validation.constraints.DecimalMax("5000")
            double height,
            @NotNull @jakarta.validation.constraints.Pattern(regexp = "TEXT|SHAPE") String kind) {
    }

    public record CanvaImport(CanvaTemplate template, PosterAgent.CanvaMapping mapping) {
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
