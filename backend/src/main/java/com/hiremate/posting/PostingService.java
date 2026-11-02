package com.hiremate.posting;

import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.company.MailStyleService;
import com.hiremate.company.PosterBrand;
import com.hiremate.company.ReceiptTemplate;
import com.hiremate.company.ReceiptTemplateService;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.global.ApiException;
import com.hiremate.global.JsonText;
import com.hiremate.mail.MailPreview;
import com.hiremate.posting.application.DummyScreeningRubric;
import com.hiremate.posting.domain.JobPosting;
import com.hiremate.posting.domain.JobPostingRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageDraft;
import com.hiremate.recruit.StageType;
import java.time.Instant;
import java.util.Arrays;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 공고 작성. 새 채용은 기업 공고 Template(설정의 회사 소개 · 복지 · 필수 안내 문구)으로 시작한다. */
@Service
public class PostingService {

    static final String DEFAULT_TITLE = "새 채용";
    static final List<StageDraft> DEFAULT_STAGES = List.of(new StageDraft("서류 전형", StageType.DOCUMENT));
    /** 수정안의 changedFields에서 전형 절차와 필수 제출 서류의 이름. 나머지는 PostingContent의 JSON 이름이다. */
    static final String STAGES_FIELD = "stages";
    static final String DOCUMENTS_FIELD = "requiredDocuments";

    private final JobPostingRepository postings;
    private final RecruitService recruits;
    private final CompanyService companies;
    private final MailStyleService mailStyles;
    private final ReceiptTemplateService receiptTemplates;
    private final ApplicationEventPublisher events;
    private final DummyScreeningRubric dummyRubric;
    private final FileService files;

    public PostingService(JobPostingRepository postings, RecruitService recruits, CompanyService companies,
            MailStyleService mailStyles, ReceiptTemplateService receiptTemplates, ApplicationEventPublisher events,
            DummyScreeningRubric dummyRubric, FileService files) {
        this.postings = postings;
        this.recruits = recruits;
        this.companies = companies;
        this.mailStyles = mailStyles;
        this.receiptTemplates = receiptTemplates;
        this.events = events;
        this.dummyRubric = dummyRubric;
        this.files = files;
    }

    @Transactional
    public PostingView createDraft(UUID companyId) {
        CompanyProfile profile = companies.profile(companyId);
        RecruitmentInfo recruitment = recruits.create(companyId, DEFAULT_TITLE, DEFAULT_STAGES);
        JobPosting posting = postings.save(new JobPosting(recruitment.id(), companyId, DEFAULT_TITLE,
                profile.intro(), profile.benefits(), companies.postingSettings(companyId).requiredNotices()));
        PosterBrand brand = companies.posterBrand(companyId);
        posting.changeDesign(new PosterDesign(PosterDesign.Template.valueOf(brand.template()),
                PosterDesign.Mood.valueOf(brand.mood()), brand.color(), brand.decoration(), false,
                brand.logoFileId() != null, brand.logoFileId()));
        return toView(posting, recruitment, profile.name());
    }

    @Transactional(readOnly = true)
    public PostingView view(UUID companyId, UUID recruitmentId) {
        return toView(posting(companyId, recruitmentId), recruits.get(companyId, recruitmentId),
                companies.profile(companyId).name());
    }

    /** AI 수정 요청에 넘길 현재 본문과 전형 절차. */
    @Transactional(readOnly = true)
    public PostingDraftContext draftContext(UUID companyId, UUID recruitmentId) {
        JobPosting posting = posting(companyId, recruitmentId);
        RecruitmentInfo recruitment = recruits.get(companyId, recruitmentId);
        return new PostingDraftContext(recruitmentId, recruitment.status(), posting.content(),
                recruitment.stages().stream()
                        .map(stage -> new StageDraft(stage.name(), stage.type(), stage.icon())).toList(),
                requiredExtras(posting));
    }

    /**
     * 서류 평가 기준(우대 사항 가중치 · NCS 능력단위 · 선발 인원). 공고 작성 화면에서 입력하기 전까지는 설정의 더미를 쓴다.
     * 다른 기업의 채용이면 404다.
     */
    @Transactional(readOnly = true)
    public ScreeningRubric screeningRubric(UUID companyId, UUID recruitmentId) {
        posting(companyId, recruitmentId);
        return dummyRubric.of(companyId, recruitmentId);
    }

    /** 본문은 게시 전에만 고칠 수 있다(requireDraft). 채용명이 바뀌면 채용 이름도 함께 바꾼다. */
    @Transactional
    public PostingView updateContent(UUID companyId, UUID recruitmentId, PostingContent content) {
        JobPosting posting = posting(companyId, recruitmentId);
        requireDraft(recruits.get(companyId, recruitmentId));
        posting.update(content);
        recruits.rename(companyId, recruitmentId, content.title());
        return view(companyId, recruitmentId);
    }

    /** 디자인 변경도 공고 게시 전에 HR이 실행한다. 타 기업 파일 ID를 주입할 수 없다. */
    @Transactional
    public PostingView updatePoster(UUID companyId, UUID recruitmentId, PosterDesign design) {
        JobPosting posting = posting(companyId, recruitmentId);
        RecruitmentInfo recruitment = recruits.get(companyId, recruitmentId);
        requireDraft(recruitment);
        if (!recruitment.stages().stream().map(stage -> stage.name()).toList()
                .containsAll(design.stageIcons().keySet())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_POSTER_STAGE", "현재 공고의 전형만 지정할 수 있어요.");
        }
        UUID logo = design.logoFileId();
        UUID oldLogo = posting.design() == null ? null : posting.design().logoFileId();
        if (logo != null && !logo.equals(oldLogo) && !logo.equals(companies.posterBrand(companyId).logoFileId())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_POSTER_LOGO", "등록한 기업 로고만 사용할 수 있어요.");
        }
        posting.changeDesign(design);
        return view(companyId, recruitmentId);
    }

    @Transactional(readOnly = true)
    public FileContent posterLogo(UUID companyId, UUID recruitmentId) {
        JobPosting posting = posting(companyId, recruitmentId);
        PosterDesign design = posting.design();
        if (design == null || !design.showLogo() || design.logoFileId() == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "LOGO_NOT_FOUND", "공고 로고가 없어요.");
        }
        return files.read(companyId, design.logoFileId());
    }

    @Transactional(readOnly = true)
    public FileContent publicPosterLogo(UUID postingId) {
        PublicPostingView published = publicView(postingId);
        if (published.poster() == null || !published.poster().enabled()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "LOGO_NOT_FOUND", "공고 로고가 없어요.");
        }
        JobPosting posting = postings.findById(postingId).orElseThrow();
        return posterLogo(posting.getCompanyId(), posting.getRecruitmentId());
    }

    @Transactional
    public PostingView suggest(UUID companyId, UUID recruitmentId, PostingSuggestion suggestion) {
        JobPosting posting = posting(companyId, recruitmentId);
        requireDraft(recruits.get(companyId, recruitmentId));
        posting.suggest(JsonText.write(suggestion));
        return view(companyId, recruitmentId);
    }

    /**
     * HR이 공고 작성 화면에서 전형 절차를 직접 정한다. 이름이 같은 전형이 둘이면 안내가 섞여 400이다.
     * 수정안에 전형 절차가 있으면 HR이 직접 정한 것을 따르고 수정안에서 뺀다. 게시한 뒤에는 바꿀 수 없다(409).
     */
    @Transactional
    public PostingView changeStages(UUID companyId, UUID recruitmentId, List<StageDraft> plan) {
        JobPosting posting = posting(companyId, recruitmentId);
        if (plan.stream().map(StageDraft::name).distinct().count() < plan.size()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "DUPLICATE_STAGE_NAME", "Stage names must be unique.");
        }
        recruits.replaceStages(companyId, recruitmentId, plan);
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        if (suggestion != null && suggestion.changedFields().contains(STAGES_FIELD)) {
            keepRest(posting, suggestion, Set.of(STAGES_FIELD));
        }
        return view(companyId, recruitmentId);
    }

    /**
     * 수정안을 적용한다. 고른 칸만 수정안으로 바꾸고, 나머지 바뀐 칸은 수정안으로 남긴다.
     *
     * @param fields 적용할 칸 이름(changedFields의 이름). 비어 있으면 바뀐 칸을 모두 적용한다
     */
    @Transactional
    public PostingView applySuggestion(UUID companyId, UUID recruitmentId, List<String> fields) {
        JobPosting posting = posting(companyId, recruitmentId);
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        if (suggestion == null) {
            throw new ApiException(HttpStatus.CONFLICT, "NO_SUGGESTION", "There is no suggestion to apply.");
        }
        Set<String> chosen = chosenFields(suggestion, fields);
        requireDraft(recruits.get(companyId, recruitmentId));
        boolean stages = chosen.contains(STAGES_FIELD) && suggestion.stages() != null;
        boolean documents = chosen.contains(DOCUMENTS_FIELD) && suggestion.requiredExtras() != null;
        PostingContent merged = merge(posting.content(), suggestion.content(), chosen);
        posting.update(merged);
        recruits.rename(companyId, recruitmentId, merged.title());
        if (stages) {
            recruits.replaceStages(companyId, recruitmentId, suggestion.stages());
        }
        if (documents) {
            posting.changeRequiredExtras(suggestion.requiredExtras().stream().map(Enum::name).sorted().toList());
        }
        keepRest(posting, suggestion, chosen);
        return view(companyId, recruitmentId);
    }

    /**
     * 수정안을 되돌린다. 고른 칸만 수정안에서 빼고 나머지는 남긴다.
     *
     * @param fields 되돌릴 칸 이름. 비어 있으면 수정안 전체를 되돌린다
     */
    @Transactional
    public PostingView discardSuggestion(UUID companyId, UUID recruitmentId, List<String> fields) {
        JobPosting posting = posting(companyId, recruitmentId);
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        if (suggestion != null) {
            keepRest(posting, suggestion, chosenFields(suggestion, fields));
        }
        return view(companyId, recruitmentId);
    }

    /** 처리할 칸. 수정안이 바꾸지 않은 칸만 골랐으면 400이다. */
    private static Set<String> chosenFields(PostingSuggestion suggestion, List<String> fields) {
        if (fields == null || fields.isEmpty()) {
            return Set.copyOf(suggestion.changedFields());
        }
        Set<String> chosen = fields.stream().filter(suggestion.changedFields()::contains).collect(Collectors.toSet());
        if (chosen.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "NOT_IN_SUGGESTION",
                    "The suggestion does not change these fields.");
        }
        return chosen;
    }

    /**
     * 처리한 칸을 뺀 수정안을 남긴다. 남은 칸이 없으면 수정안을 지운다.
     * 남은 수정안의 본문은 지금 공고에서 남은 칸만 수정안으로 바꾼 것이다. 그 사이 HR이 고친 칸을 덮지 않는다.
     */
    private static void keepRest(JobPosting posting, PostingSuggestion suggestion, Set<String> done) {
        List<String> rest = suggestion.changedFields().stream().filter(field -> !done.contains(field)).toList();
        if (rest.isEmpty()) {
            posting.clearSuggestion();
            return;
        }
        Set<String> restFields = Set.copyOf(rest);
        posting.suggest(JsonText.write(new PostingSuggestion(merge(posting.content(), suggestion.content(), restFields),
                restFields.contains(STAGES_FIELD) ? suggestion.stages() : null,
                restFields.contains(DOCUMENTS_FIELD) ? suggestion.requiredExtras() : null, rest)));
    }

    /** fields에 있는 칸만 suggested에서, 나머지는 current에서 가져온다. 칸 이름은 PostingContent의 JSON 이름이다. */
    private static PostingContent merge(PostingContent current, PostingContent suggested, Set<String> fields) {
        return new PostingContent(
                pick(fields, "title", current.title(), suggested.title()),
                pick(fields, "jobCategory", current.jobCategory(), suggested.jobCategory()),
                pick(fields, "employmentType", current.employmentType(), suggested.employmentType()),
                pick(fields, "career", current.career(), suggested.career()),
                pick(fields, "location", current.location(), suggested.location()),
                pick(fields, "intro", current.intro(), suggested.intro()),
                pick(fields, "duties", current.duties(), suggested.duties()),
                pick(fields, "qualifications", current.qualifications(), suggested.qualifications()),
                pick(fields, "preferred", current.preferred(), suggested.preferred()),
                pick(fields, "benefits", current.benefits(), suggested.benefits()),
                pick(fields, "headcount", current.headcount(), suggested.headcount()),
                pick(fields, "position", current.position(), suggested.position()),
                pick(fields, "education", current.education(), suggested.education()),
                pick(fields, "workHours", current.workHours(), suggested.workHours()),
                pick(fields, "salary", current.salary(), suggested.salary()),
                pick(fields, "roles", current.roles(), suggested.roles()));
    }

    private static <T> T pick(Set<String> fields, String name, T current, T suggested) {
        return fields.contains(name) ? suggested : current;
    }

    /** 지원자에게 보낼 접수 확인 메일. 보내는 때의 설정 › 안내 메일 양식에 지원자 값을 채우고 필수 문구를 붙인다. */
    @Transactional(readOnly = true)
    public ReceiptMail receiptMail(UUID companyId, UUID recruitmentId, String applicantName, int applicationNo) {
        JobPosting posting = posting(companyId, recruitmentId);
        String companyName = companies.profile(companyId).name();
        ReceiptTemplate filled = receiptTemplates.template(companyId).fill(companyName, posting.getTitle(),
                applicantName, applicationNo);
        return new ReceiptMail(filled.subject(), filled.toMail(companyName, posting.getTitle()),
                mailStyles.brand(companyId));
    }

    /** 게시 화면에 보여 줄 접수 확인 메일. 지금 설정의 양식으로 만들고 지원자 이름과 지원번호는 예시다. */
    @Transactional(readOnly = true)
    public MailPreview receiptPreview(UUID companyId, UUID recruitmentId) {
        ReceiptMail receipt = receiptMail(companyId, recruitmentId, "홍길동", 1);
        return MailPreview.of(receipt.subject(), receipt.content(), receipt.brand());
    }

    /** HR이 접수 기간을 정해 게시한다. AI는 게시하지 않는다. */
    @Transactional
    public PostingView publish(UUID companyId, UUID recruitmentId, UUID memberId, Instant openAt, Instant closeAt) {
        if (!closeAt.isAfter(openAt) || !closeAt.isAfter(Instant.now())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PERIOD", "Check the application period.");
        }
        JobPosting posting = posting(companyId, recruitmentId);
        recruits.publish(companyId, recruitmentId);
        posting.publish(openAt, closeAt, memberId);
        return view(companyId, recruitmentId);
    }

    /** 접수를 마감하고 첫 전형을 시작한다. 이미 마감했으면 그대로 둔다. */
    @Transactional
    public PostingView close(UUID companyId, UUID recruitmentId) {
        JobPosting posting = posting(companyId, recruitmentId);
        if (posting.getPublishedAt() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "POSTING_NOT_PUBLISHED", "The posting is not published.");
        }
        if (posting.getClosedAt() == null) {
            posting.close();
            recruits.startFirstStage(companyId, recruitmentId).ifPresent(stage ->
                    events.publishEvent(new PostingClosed(recruitmentId, companyId, stage.id())));
        }
        return view(companyId, recruitmentId);
    }

    /** 접수 기간이 끝난 공고를 찾아 마감한다. */
    @Transactional
    public int closeExpired(Instant now) {
        List<JobPosting> expired = postings.findByClosedAtIsNullAndCloseAtBefore(now);
        expired.forEach(posting -> close(posting.getCompanyId(), posting.getRecruitmentId()));
        return expired.size();
    }

    /** 지원자용 공고. 게시하지 않은 공고는 찾지 못한 것으로 다룬다. */
    @Transactional(readOnly = true)
    public PublicPostingView publicView(UUID postingId) {
        JobPosting posting = postings.findById(postingId)
                .filter(found -> found.getPublishedAt() != null)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "POSTING_NOT_FOUND", "Posting not found."));
        RecruitmentInfo recruitment = recruits.get(posting.getCompanyId(), posting.getRecruitmentId());
        CompanyProfile company = companies.profile(posting.getCompanyId());
        return new PublicPostingView(posting.getId(), company.name(),
                posting.content(), List.copyOf(posting.getNotices()),
                recruitment.stages().stream()
                        .map(stage -> new PublicPostingView.PublicStage(stage.name(), stage.type(), stage.icon()))
                        .toList(),
                documents(requiredExtras(posting)), posting.getOpenAt(), posting.getCloseAt(),
                state(posting, Instant.now()), posting.design(), company.address());
    }

    /** 지원서 접수에 필요한 공고 정보. 접수 중이 아니면 409다. */
    @Transactional(readOnly = true)
    public ApplicationTarget openTarget(UUID postingId) {
        PublicPostingView view = publicView(postingId);
        if (view.state() != PublicPostingView.State.OPEN) {
            throw new ApiException(HttpStatus.CONFLICT, "POSTING_NOT_OPEN", "The posting is not open.");
        }
        JobPosting posting = postings.findById(postingId).orElseThrow();
        return new ApplicationTarget(posting.getId(), posting.getRecruitmentId(), posting.getCompanyId(),
                view.companyName(), posting.getTitle(), requiredExtras(posting));
    }

    static PublicPostingView.State state(JobPosting posting, Instant now) {
        if (posting.getClosedAt() != null || !now.isBefore(posting.getCloseAt())) {
            return PublicPostingView.State.CLOSED;
        }
        return now.isBefore(posting.getOpenAt()) ? PublicPostingView.State.UPCOMING : PublicPostingView.State.OPEN;
    }

    JobPosting posting(UUID companyId, UUID recruitmentId) {
        return postings.findByRecruitmentIdAndCompanyId(recruitmentId, companyId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "POSTING_NOT_FOUND", "Posting not found."));
    }

    /**
     * 게시한 공고는 본문 · 전형 절차 · 필수 제출 서류를 바꿀 수 없다. 모든 지원자가 같은 공고를 보고 지원하게 한다.
     * 일정 · 장소가 바뀔 수 있는 전형별 안내만 채용이 끝나기 전까지 고칠 수 있다 (NoticeService.changeGuide).
     */
    private static void requireDraft(RecruitmentInfo recruitment) {
        if (recruitment.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED", "A published posting cannot change.");
        }
    }

    static Set<DocumentType> requiredExtras(JobPosting posting) {
        Set<DocumentType> extras = EnumSet.noneOf(DocumentType.class);
        posting.getRequiredExtras().forEach(name -> extras.add(DocumentType.valueOf(name)));
        return extras;
    }

    static List<RequiredDocument> documents(Set<DocumentType> extras) {
        return Arrays.stream(DocumentType.values())
                .map(type -> new RequiredDocument(type, type.label(), type.format(),
                        type.alwaysRequired() || extras.contains(type)))
                .toList();
    }

    private PostingView toView(JobPosting posting, RecruitmentInfo recruitment, String companyName) {
        List<PostingView.PostingStage> stages = recruitment.stages().stream()
                .map(stage -> new PostingView.PostingStage(stage.id(), stage.name(), stage.type(), stage.status(),
                        stage.icon()))
                .toList();
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        PostingView.PostingSuggestionView suggestionView = suggestion == null
                ? null
                : new PostingView.PostingSuggestionView(
                suggestion.content(),
                suggestion.stages() == null ? null : suggestion.stages().stream()
                        .map(stage -> new PostingView.PostingStage(
                                null, stage.name(), stage.type(), null, stage.icon()))
                        .toList(),
                suggestion.requiredExtras() == null ? null : documents(suggestion.requiredExtras()),
                suggestion.changedFields());
        return new PostingView(posting.getId(), recruitment.id(), companyName, recruitment.status(),
                posting.content(), List.copyOf(posting.getNotices()), stages, documents(requiredExtras(posting)),
                posting.getOpenAt(), posting.getCloseAt(), posting.getPublishedAt(), posting.getClosedAt(),
                suggestionView, posting.design());
    }
}
