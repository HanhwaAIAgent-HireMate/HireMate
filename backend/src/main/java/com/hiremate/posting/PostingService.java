package com.hiremate.posting;

import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.global.ApiException;
import com.hiremate.global.JsonText;
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
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 공고 작성. 새 채용은 기업 공고 Template(설정의 회사 소개 · 복지 · 필수 안내 문구)으로 시작한다. */
@Service
public class PostingService {

    static final String DEFAULT_TITLE = "새 채용";
    static final List<StageDraft> DEFAULT_STAGES = List.of(new StageDraft("서류 전형", StageType.DOCUMENT));

    private final JobPostingRepository postings;
    private final RecruitService recruits;
    private final CompanyService companies;
    private final ApplicationEventPublisher events;
    private final DummyScreeningRubric dummyRubric;

    public PostingService(JobPostingRepository postings, RecruitService recruits, CompanyService companies,
            ApplicationEventPublisher events, DummyScreeningRubric dummyRubric) {
        this.postings = postings;
        this.recruits = recruits;
        this.companies = companies;
        this.events = events;
        this.dummyRubric = dummyRubric;
    }

    @Transactional
    public PostingView createDraft(UUID companyId) {
        CompanyProfile profile = companies.profile(companyId);
        RecruitmentInfo recruitment = recruits.create(companyId, DEFAULT_TITLE, DEFAULT_STAGES);
        JobPosting posting = postings.save(new JobPosting(recruitment.id(), companyId, DEFAULT_TITLE,
                profile.intro(), profile.benefits(), companies.postingSettings(companyId).requiredNotices()));
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
                recruitment.stages().stream().map(stage -> new StageDraft(stage.name(), stage.type())).toList(),
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

    /** 본문은 게시 후에도 고칠 수 있다. 채용명이 바뀌면 채용 이름도 함께 바꾼다. */
    @Transactional
    public PostingView updateContent(UUID companyId, UUID recruitmentId, PostingContent content) {
        JobPosting posting = posting(companyId, recruitmentId);
        requireEditable(recruits.get(companyId, recruitmentId));
        posting.update(content);
        recruits.rename(companyId, recruitmentId, content.title());
        return view(companyId, recruitmentId);
    }

    @Transactional
    public PostingView suggest(UUID companyId, UUID recruitmentId, PostingSuggestion suggestion) {
        JobPosting posting = posting(companyId, recruitmentId);
        requireEditable(recruits.get(companyId, recruitmentId));
        posting.suggest(JsonText.write(suggestion));
        return view(companyId, recruitmentId);
    }

    @Transactional
    public PostingView applySuggestion(UUID companyId, UUID recruitmentId) {
        JobPosting posting = posting(companyId, recruitmentId);
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        if (suggestion == null) {
            throw new ApiException(HttpStatus.CONFLICT, "NO_SUGGESTION", "There is no suggestion to apply.");
        }
        RecruitmentInfo recruitment = recruits.get(companyId, recruitmentId);
        requireEditable(recruitment);
        boolean changesProcess = suggestion.stages() != null || suggestion.requiredExtras() != null;
        if (changesProcess && recruitment.status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED",
                    "Stages and required documents cannot change after publishing.");
        }
        posting.update(suggestion.content());
        recruits.rename(companyId, recruitmentId, suggestion.content().title());
        if (suggestion.stages() != null) {
            recruits.replaceStages(companyId, recruitmentId, suggestion.stages());
        }
        if (suggestion.requiredExtras() != null) {
            posting.changeRequiredExtras(suggestion.requiredExtras().stream().map(Enum::name).sorted().toList());
        }
        posting.clearSuggestion();
        return view(companyId, recruitmentId);
    }

    @Transactional
    public PostingView discardSuggestion(UUID companyId, UUID recruitmentId) {
        posting(companyId, recruitmentId).clearSuggestion();
        return view(companyId, recruitmentId);
    }

    /** 접수 확인 메일은 게시 전에만 고칠 수 있다. 게시한 뒤에는 모든 지원자가 같은 메일을 받는다. */
    @Transactional
    public PostingView changeReceipt(UUID companyId, UUID recruitmentId, ReceiptTemplate receipt) {
        JobPosting posting = posting(companyId, recruitmentId);
        if (recruits.get(companyId, recruitmentId).status() != RecruitmentStatus.DRAFT) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED",
                    "The receipt mail cannot change after publishing.");
        }
        posting.changeReceipt(receipt);
        return view(companyId, recruitmentId);
    }

    /** 지원자에게 보낼 접수 확인 메일. 공고의 템플릿에 지원자 값을 채우고 필수 문구를 붙인다. */
    @Transactional(readOnly = true)
    public ReceiptTemplate receiptMail(UUID companyId, UUID recruitmentId, String applicantName, int applicationNo) {
        JobPosting posting = posting(companyId, recruitmentId);
        return posting.receipt().fill(companies.profile(companyId).name(), posting.getTitle(), applicantName,
                applicationNo);
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
        return new PublicPostingView(posting.getId(), companies.profile(posting.getCompanyId()).name(),
                posting.content(), List.copyOf(posting.getNotices()),
                recruitment.stages().stream()
                        .map(stage -> new PublicPostingView.PublicStage(stage.name(), stage.type()))
                        .toList(),
                documents(requiredExtras(posting)), posting.getOpenAt(), posting.getCloseAt(),
                state(posting, Instant.now()));
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

    private static void requireEditable(RecruitmentInfo recruitment) {
        if (recruitment.status() != RecruitmentStatus.DRAFT && recruitment.status() != RecruitmentStatus.PUBLISHED) {
            throw new ApiException(HttpStatus.CONFLICT, "POSTING_CLOSED", "The posting can no longer be edited.");
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
                .map(stage -> new PostingView.PostingStage(stage.id(), stage.name(), stage.type()))
                .toList();
        PostingSuggestion suggestion = JsonText.read(posting.getPendingSuggestion(), PostingSuggestion.class);
        PostingView.PostingSuggestionView suggestionView = suggestion == null
                ? null
                : new PostingView.PostingSuggestionView(
                suggestion.content(),
                suggestion.stages() == null ? null : suggestion.stages().stream()
                        .map(stage -> new PostingView.PostingStage(null, stage.name(), stage.type()))
                        .toList(),
                suggestion.requiredExtras() == null ? null : documents(suggestion.requiredExtras()),
                suggestion.changedFields());
        return new PostingView(posting.getId(), recruitment.id(), companyName, recruitment.status(),
                posting.content(), List.copyOf(posting.getNotices()), stages, documents(requiredExtras(posting)),
                posting.getOpenAt(), posting.getCloseAt(), posting.getPublishedAt(), posting.getClosedAt(),
                suggestionView, new PostingView.ReceiptView(posting.receipt().subject(), posting.receipt().body(),
                        ReceiptTemplate.REQUIRED_TEXT));
    }
}
