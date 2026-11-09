package com.hiremate.ai.api;

import com.hiremate.ai.application.PosterAgent;
import com.hiremate.company.CanvaConnectionService;
import com.hiremate.company.CanvaConnectionService.CanvaTemplate;
import com.hiremate.company.CompanyService;
import com.hiremate.company.PosterBrand;
import com.hiremate.company.PosterTemplate;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.OrshotLibrary;
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
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

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
    private final OrshotLibrary orshot;

    public PosterAiController(PostingService postings, CompanyService companies, PosterAgent agent,
            Validator validator, CanvaConnectionService canva, TemplatedLibrary templates,
            PosterTemplateSearch templateSearch, OrshotLibrary orshot) {
        this.postings = postings;
        this.companies = companies;
        this.agent = agent;
        this.validator = validator;
        this.canva = canva;
        this.templates = templates;
        this.templateSearch = templateSearch;
        this.orshot = orshot;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/ai-requests")
    public PosterProposal design(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PosterAiRequest request, HttpSession session) {
        return designWithProgress(member, recruitmentId, request, session, step -> { });
    }

    PosterProposal designWithProgress(AuthenticatedMember member, UUID recruitmentId,
            PosterAiRequest request, HttpSession session, Consumer<String> progress) {
        progress.accept("공고와 기업 정보를 확인하고 있어요");
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        PosterBrand brand = companies.posterBrand(member.companyId());
        PosterDesign current = request.design() == null ? posting.poster() : request.design();
        Set<String> excluded = new HashSet<>();
        brand.templates().forEach(item -> excluded.add(PosterTemplate.sourceId(item.canvasJson())));
        if (current != null) {
            excluded.add(PosterTemplate.sourceId(current.canvasJson()));
        }
        request.history().forEach(turn -> turn.recommendations().forEach(item ->
                excluded.add(PosterTemplate.sourceId(item.design().canvasJson()))));
        excluded.remove("");
        UUID logo = current == null ? null : current.logoFileId();
        UUID savedLogo = posting.poster() == null ? null : posting.poster().logoFileId();
        if (logo != null && !logo.equals(savedLogo) && !logo.equals(brand.logoFileId())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_POSTER_LOGO", "등록한 기업 로고만 사용할 수 있어요.");
        }
        PosterContext context = new PosterContext(companies.profile(member.companyId()), posting.content(),
                current, brand.color(), request.history(),
                posting.stages().stream().map(PostingView.PostingStage::name).toList(), request.sectionNames(),
                canva.status(member, session).connected(), posting.stages().stream().collect(Collectors.toMap(
                        PostingView.PostingStage::name, stage -> displayedIcon(stage, current))));
        progress.accept("요청에 맞는 포스터 디자인을 구상하고 있어요");
        PosterProposal proposal = agent.design(context, request.message());
        if (!validator.validate(proposal).isEmpty()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_POSTER_PROPOSAL", "디자인 수정안을 확인하지 못했어요.");
        }
        if (proposal.externalQuery() != null && proposal.candidateMode() != null) {
            progress.accept("템플릿 후보를 조회하고 새 디자인을 준비하고 있어요");
            request.history().forEach(turn -> turn.templates().forEach(template -> excluded.add(template.id())));
            return plannedCandidates(proposal, context, request.message(), logo, excluded);
        }
        if (proposal.externalQuery() != null) {
            progress.accept("연결된 서비스에서 템플릿 후보를 찾고 있어요");
            List<PosterProposal.FreeTemplate> candidates = new ArrayList<>();
            List<CanvaConnectionService.CanvaDesign> canvaCandidates = List.of();
            String unavailable = "";
            String searched = "";
            try {
                candidates.addAll(templates.searchGallery(proposal.externalQuery(), excluded));
                searched = "Templated";
            } catch (ApiException exception) {
                unavailable = "TEMPLATED_NOT_CONFIGURED".equals(exception.code())
                        ? " Templated 연결 설정이 필요해요."
                        : " Templated 조회에 실패했어요. 잠시 후 다시 요청해 주세요.";
            }
            try {
                List<PosterProposal.FreeTemplate> orshotCandidates = orshot.search(proposal.externalQuery(), excluded);
                for (int index = 0; index < orshotCandidates.size(); index++) {
                    candidates.add(Math.min(index * 2 + 1, candidates.size()), orshotCandidates.get(index));
                }
                searched += searched.isEmpty() ? "Orshot" : "·Orshot";
            } catch (ApiException exception) {
                if (!"ORSHOT_NOT_CONFIGURED".equals(exception.code())) {
                    unavailable += " Orshot 조회에 실패했어요.";
                }
            }
            if (context.canvaConnected()) {
                try {
                    canvaCandidates = canva.search(member, session,
                            proposal.canvaQuery() == null ? proposal.externalQuery() : proposal.canvaQuery(), excluded);
                    searched += searched.isEmpty() ? "Canva 내 디자인" : "와 Canva 내 디자인";
                } catch (ApiException exception) {
                    unavailable += " Canva에 연결하지 못했어요.";
                }
            }
            var combined = templateSearch.combine(candidates, canvaCandidates, excluded);
            int count = combined.templates().size() + combined.designs().size();
            List<PosterProposal.Recommendation> generated = count < 2
                    ? generateAlternatives(context, request.message(), logo) : List.of();
            String reply = count == 0
                    ? "가져올 수 있는 새 외부 템플릿을 찾지 못했어요."
                    : searched + "에서 아직 추가하지 않은 외부 템플릿 " + count + "개를 찾았어요.";
            if (!generated.isEmpty()) {
                reply += " 요청에 맞춰 HireMate에서 새 디자인 " + generated.size() + "개도 만들었어요.";
            }
            return new PosterProposal(reply + unavailable, generated, combined.templates(),
                    null, null, combined.designs());
        }
        if (proposal.canvaQuery() != null) {
            progress.accept("연결된 Canva 디자인을 찾고 있어요");
            var designs = canva.search(member, session, proposal.canvaQuery(), excluded);
            return new PosterProposal(designs.isEmpty()
                    ? "Canva 계정에서 일치하는 디자인을 찾지 못했어요. Canva에 저장한 디자인 이름으로 요청해 주세요."
                    : "연결한 Canva 계정에서 중복을 제외한 디자인 " + designs.size()
                            + "개를 찾았어요. 미리보기를 확인하고 선택해 주세요.",
                    List.of(), List.of(), null, null, designs);
        }
        return new PosterProposal(proposal.reply(), secureRecommendations(proposal, context, logo),
                proposal.templates(), proposal.selectedTemplateId());
    }

    private PosterProposal plannedCandidates(PosterProposal proposal, PosterContext context, String message,
            UUID logo, Set<String> excluded) {
        var mode = proposal.candidateMode();
        boolean motion = mode == PosterProposal.CandidateMode.MOTION;
        List<PosterProposal.FreeTemplate> external = new ArrayList<>();
        String unavailable = "";
        boolean foundTemplated = false;
        if (mode == PosterProposal.CandidateMode.INITIAL) {
            try {
                var found = templates.searchGallery(proposal.externalQuery(), excluded).stream().limit(1).toList();
                external.addAll(found);
                foundTemplated = !found.isEmpty();
            } catch (ApiException exception) {
                unavailable += " Templated 후보를 불러오지 못했어요.";
            }
        }
        try {
            external.addAll(orshot.search(proposal.externalQuery(), excluded, motion)
                    .stream().limit(motion ? 2 : 1).toList());
        } catch (ApiException exception) {
            unavailable += " Orshot 후보를 불러오지 못했어요.";
        }
        List<PosterProposal.Recommendation> generated = motion ? List.of()
                : generateAlternatives(context, message, logo).stream()
                        .limit(mode == PosterProposal.CandidateMode.INITIAL && !foundTemplated ? 2 : 1).toList();
        if (!generated.isEmpty()) {
            var first = generated.getFirst();
            ObjectNode canvas = (ObjectNode) new JsonMapper().readTree(first.design().canvasJson());
            canvas.put("templatedRegistration", true);
            PosterDesign design = first.design();
            var registered = new PosterProposal.Recommendation(new PosterDesign(
                    design.template(), design.mood(), design.color(), design.decoration(), design.enabled(),
                    design.showLogo(), design.logoFileId(), design.backgroundStyle(), design.stageIcons(),
                    design.readableSections(), canvas.toString(), design.tagline(), design.motion()), first.reason());
            generated = java.util.stream.Stream.concat(java.util.stream.Stream.of(registered),
                    generated.stream().skip(1)).toList();
        }
        if (!motion && generated.isEmpty()) {
            unavailable += " 자체 생성 후보를 만들지 못했어요.";
        }
        int count = external.size() + generated.size();
        String reply = count == 0
                ? "아직 보여드릴 수 있는 새 디자인이 없어요. 원하는 분위기나 구성을 바꿔 요청해 주세요."
                : (motion ? "움직이는 포스터 " : "정적 포스터 ") + count
                        + "개를 준비했어요. 공고를 채운 미리보기를 비교해 주세요.";
        return new PosterProposal(reply + unavailable, generated, external);
    }

    private List<PosterProposal.Recommendation> generateAlternatives(PosterContext context, String message, UUID logo) {
        try {
            PosterProposal proposal = agent.generate(context, message);
            if (!validator.validate(proposal).isEmpty()) {
                return List.of();
            }
            return secureRecommendations(proposal, context, logo).stream()
                    .filter(item -> PosterTemplate.sourceId(item.design().canvasJson()).startsWith("generated:"))
                    .toList();
        } catch (ApiException exception) {
            // 자체 생성이 실패하더라도 이미 찾은 외부 후보는 보여 준다.
            return List.of();
        }
    }

    private static List<PosterProposal.Recommendation> secureRecommendations(
            PosterProposal proposal, PosterContext context, UUID logo) {
        if (proposal.recommendations().stream().anyMatch(item ->
                !context.stageNames().containsAll(item.design().stageIcons().keySet()))) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "INVALID_POSTER_PROPOSAL", "전형 아이콘 수정안을 확인하지 못했어요.");
        }
        // AI가 만든 파일 ID는 신뢰하지 않고 현재 공고 로고를 보존한다.
        return proposal.recommendations().stream().map(item -> {
            PosterDesign design = item.design();
            return new PosterProposal.Recommendation(new PosterDesign(design.template(), design.mood(),
                    design.color(), design.decoration(), design.enabled(), design.showLogo() && logo != null, logo,
                    design.backgroundStyle(), design.stageIcons(), design.readableSections(), design.canvasJson(),
                    design.tagline(), design.motion()),
                    item.reason());
        }).toList();
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

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/orshot-import")
    public OrshotLibrary.OrshotTemplate importOrshot(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody OrshotImportRequest request) {
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        return orshot.renderOriginal(request.templateId(), posting);
    }

    public record OrshotImportRequest(@jakarta.validation.constraints.Min(1) long templateId) {
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/poster/templated-register")
    public TemplatedLibrary.RegisteredTemplate registerTemplated(AuthenticatedMember member,
            @PathVariable UUID recruitmentId, @Valid @RequestBody TemplatedRegisterRequest request) {
        PostingView posting = postings.view(member.companyId(), recruitmentId);
        if (posting.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "게시한 공고는 바꿀 수 없어요.");
        }
        return templates.register(member.companyId(), request.sourceId(),
                request.name(), request.svg(), request.height());
    }

    public record TemplatedRegisterRequest(
            @NotBlank @jakarta.validation.constraints.Pattern(regexp = "generated:[a-fA-F0-9-]{36}") String sourceId,
            @NotBlank @Size(max = 100) String name,
            @NotBlank @Size(max = 1000000) String svg,
            @jakarta.validation.constraints.Min(300) @jakarta.validation.constraints.Max(5000) int height) {
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
