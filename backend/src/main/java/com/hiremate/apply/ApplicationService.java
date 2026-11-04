package com.hiremate.apply;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.PdfText;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import com.hiremate.posting.ApplicationTarget;
import com.hiremate.posting.BlindMask;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 지원 접수와 지원서 조회 (FR-06 ~ FR-08). */
@Service
public class ApplicationService {

    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    private static final Pattern PHONE = Pattern.compile("^[0-9+\\-() ]{9,20}$");

    private final JobApplicationRepository applications;
    private final ApplicationDocumentRepository documents;
    private final PostingService postings;
    private final FileService files;
    private final ApplicationEventPublisher events;
    private final RecruitService recruits;

    public ApplicationService(JobApplicationRepository applications, ApplicationDocumentRepository documents,
            PostingService postings, FileService files, ApplicationEventPublisher events, RecruitService recruits) {
        this.applications = applications;
        this.documents = documents;
        this.postings = postings;
        this.files = files;
        this.events = events;
        this.recruits = recruits;
    }

    /** 필수 항목이 비면 접수하지 않는다. 같은 채용에 같은 이메일로 두 번 지원할 수 없다 (NFR-06). */
    @Transactional
    public SubmittedApplication submit(UUID postingId, ApplicationForm form) {
        ApplicationTarget target = postings.openTarget(postingId);
        String email = form.email() == null ? "" : form.email().trim().toLowerCase(Locale.ROOT);
        String name = form.name() == null ? "" : form.name().trim();
        String phone = form.phone() == null ? "" : form.phone().trim();
        String certificates = form.certificates() == null || form.certificates().isBlank()
                ? null : form.certificates().trim();
        boolean missing = name.isEmpty() || name.length() > 100 || !EMAIL.matcher(email).matches()
                || email.length() > 254 || !PHONE.matcher(phone).matches()
                || !form.consentPrivacy() || !form.consentAi() || form.resume() == null || form.coverLetter() == null
                || target.requiredExtras().contains(DocumentType.PORTFOLIO) && form.portfolio() == null
                || target.requiredExtras().contains(DocumentType.CERTIFICATE) && certificates == null
                || certificates != null && certificates.length() > 1000;
        if (missing) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "Fill in the required items.");
        }
        if (applications.existsByRecruitmentIdAndEmail(target.recruitmentId(), email)) {
            throw new ApiException(HttpStatus.CONFLICT, "ALREADY_APPLIED", "This email has already applied.");
        }
        JobApplication application = applications.save(new JobApplication(target.recruitmentId(),
                target.companyId(), postingId, applications.maxApplicationNo(target.recruitmentId()) + 1, name, email,
                phone, certificates));
        saveDocument(application, DocumentType.RESUME, form.resume(), target.blind());
        saveDocument(application, DocumentType.COVER_LETTER, form.coverLetter(), target.blind());
        if (form.portfolio() != null) {
            saveDocument(application, DocumentType.PORTFOLIO, form.portfolio(), target.blind());
        }
        events.publishEvent(new ApplicationSubmitted(application.getId(), target.recruitmentId(), target.companyId()));
        return new SubmittedApplication(application.getApplicationNo(), name, target.companyName(),
                target.postingTitle());
    }

    /** 블라인드 채용이면 제출 전에 서류에서 찾은 학교 이름을 알려 준다. 제출을 막지는 않는다. 파일이 없으면 null이다. */
    @Transactional(readOnly = true)
    public SchoolCheck checkSchools(UUID postingId, ApplicationForm.Upload resume, ApplicationForm.Upload coverLetter,
            ApplicationForm.Upload portfolio) {
        if (!postings.openTarget(postingId).blind()) {
            return new SchoolCheck(List.of());
        }
        List<SchoolCheck.Found> found = new ArrayList<>();
        Map<DocumentType, ApplicationForm.Upload> uploads = new LinkedHashMap<>();
        uploads.put(DocumentType.RESUME, resume);
        uploads.put(DocumentType.COVER_LETTER, coverLetter);
        uploads.put(DocumentType.PORTFOLIO, portfolio);
        uploads.forEach((type, upload) -> {
            List<String> names = upload == null ? List.of() : BlindMask.schoolNames(PdfText.extract(upload.content()));
            if (!names.isEmpty()) {
                found.add(new SchoolCheck.Found(type, names));
            }
        });
        return new SchoolCheck(found);
    }

    /** 접수 현황. 최근에 지원한 순서다. */
    @Transactional(readOnly = true)
    public ApplicationPage page(UUID companyId, UUID recruitmentId, int page, int size) {
        Page<JobApplication> found = applications.findByRecruitmentIdAndCompanyIdOrderBySubmittedAtDesc(
                recruitmentId, companyId, PageRequest.of(Math.max(page, 0), Math.clamp(size, 1, 100)));
        Map<UUID, List<DocumentType>> types = documents
                .findByApplicationIdIn(found.stream().map(JobApplication::getId).toList()).stream()
                .collect(Collectors.groupingBy(ApplicationDocument::getApplicationId,
                        Collectors.mapping(ApplicationDocument::getType, Collectors.toList())));
        boolean hidden = hidesIdentity(companyId, recruitmentId);
        return new ApplicationPage(found.getTotalElements(), found.stream()
                .map(application -> {
                    List<DocumentType> submitted = new ArrayList<>(types.getOrDefault(application.getId(), List.of()));
                    if (application.getCertificates() != null) {
                        submitted.add(DocumentType.CERTIFICATE);
                    }
                    submitted.sort(Comparator.naturalOrder());
                    return new ApplicationSummary(application.getId(), application.getApplicationNo(),
                            hidden ? ApplicantInfo.blindName(application.getApplicationNo()) : application.getName(),
                            application.getSubmittedAt(), submitted);
                })
                .toList());
    }

    @Transactional(readOnly = true)
    public long count(UUID companyId, UUID recruitmentId) {
        return applications.countByRecruitmentIdAndCompanyId(recruitmentId, companyId);
    }

    @Transactional(readOnly = true)
    public List<ApplicantInfo> applicants(UUID companyId, UUID recruitmentId) {
        Identity identity = new Identity(companyId);
        return applications.findByRecruitmentIdAndCompanyId(recruitmentId, companyId).stream()
                .map(identity::info)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<ApplicantInfo> applicants(UUID companyId, List<UUID> applicationIds) {
        Identity identity = new Identity(companyId);
        return applications.findByIdInAndCompanyId(applicationIds, companyId).stream()
                .map(identity::info)
                .toList();
    }

    /**
     * 지원자의 실제 이름과 이메일. 블라인드 채용에서도 가리지 않으므로 메일 발송과 외부 평가 결과 매칭에만 쓰고, 화면이나 AI로
     * 넘기지 않는다.
     */
    @Transactional(readOnly = true)
    public List<ApplicantContact> contacts(UUID companyId, Collection<UUID> applicationIds) {
        return applications.findByIdInAndCompanyId(List.copyOf(applicationIds), companyId).stream()
                .map(application -> new ApplicantContact(application.getId(), application.getApplicationNo(),
                        application.getName(), application.getEmail()))
                .toList();
    }

    /** 채용 지원자 전원의 제출 문서. AI Chat이 후보의 근거를 찾을 때 쓴다. */
    @Transactional(readOnly = true)
    public Map<UUID, List<ApplicantDocument>> documents(UUID companyId, UUID recruitmentId) {
        Map<UUID, JobApplication> byId = applications.findByRecruitmentIdAndCompanyId(recruitmentId, companyId)
                .stream()
                .collect(Collectors.toMap(JobApplication::getId, Function.identity()));
        Identity identity = new Identity(companyId);
        return documents.findByApplicationIdIn(List.copyOf(byId.keySet())).stream()
                .sorted(Comparator.comparing(ApplicationDocument::getType))
                .collect(Collectors.groupingBy(ApplicationDocument::getApplicationId,
                        Collectors.mapping(document -> identity.document(byId.get(document.getApplicationId()),
                                document), Collectors.toList())));
    }

    /** 제출 문서 본문에 낱말이 들어 있는 지원서. */
    @Transactional(readOnly = true)
    public List<UUID> searchDocuments(UUID companyId, UUID recruitmentId, String keyword) {
        List<UUID> found = documents.searchText(recruitmentId, companyId, keyword);
        if (found.isEmpty() || !hidesIdentity(companyId, recruitmentId)) {
            return found;
        }
        // 저장한 본문은 가리기 전 글이라, 실제 이름 · 이메일 · 전화번호로 찾으면 그 지원자를 결과에서 뺀다
        Set<UUID> revealing = applications.findByIdInAndCompanyId(found, companyId).stream()
                .filter(application -> !BlindMask.maskApplicant(keyword, application.getName())
                        .equals(BlindMask.maskApplicant(keyword, "")))
                .map(JobApplication::getId)
                .collect(Collectors.toSet());
        String withoutContacts = BlindMask.maskApplicant(keyword, "");
        if (!withoutContacts.equals(keyword)) {
            return List.of();
        }
        return found.stream().filter(id -> !revealing.contains(id)).toList();
    }

    @Transactional(readOnly = true)
    public ApplicantDetail detail(UUID companyId, UUID applicationId) {
        JobApplication application = application(companyId, applicationId);
        Identity identity = new Identity(companyId);
        return new ApplicantDetail(identity.info(application),
                identity.hides(application) ? "" : application.getPhone(), application.getCertificates(),
                documents.findByApplicationId(applicationId).stream()
                        .sorted(Comparator.comparing(ApplicationDocument::getType))
                        .map(document -> identity.document(application, document))
                        .toList());
    }

    /** 분석 Agent가 정리한 결과. 회사 범위 검증은 이벤트를 발행한 접수 단계에서 끝났다. */
    @Transactional
    public void recordAnalysis(UUID applicationId, ApplicationAnalysis analysis) {
        applications.findById(applicationId).ifPresent(application -> application.recordAnalysis(analysis));
    }

    /** 지원서의 기업 ID. 이벤트로 받은 지원서라 기업 범위 확인 없이 읽는다. */
    @Transactional(readOnly = true)
    public UUID companyOf(UUID applicationId) {
        return applications.findById(applicationId).orElseThrow(ApplicationService::notFound).getCompanyId();
    }

    /** 상 · 중으로 판정한 인재상을 남긴다. 상은 전체 지원자 정렬에, 상 · 중은 전체 지원자 거르기에 쓴다. */
    @Transactional
    public void recordTalents(UUID applicationId, List<String> high, List<String> mid) {
        applications.findById(applicationId).ifPresent(application -> application.recordTalents(high, mid));
    }

    @Transactional
    public void markAnalysisFailed(UUID applicationId) {
        applications.findById(applicationId).ifPresent(JobApplication::markAnalysisFailed);
    }

    /** 분석에 실패한 지원서를 다시 분석한다 (NFR-05). 분석 중이거나 끝난 지원서는 409다. */
    @Transactional
    public void retryAnalysis(UUID companyId, UUID recruitmentId, UUID applicationId) {
        JobApplication application = application(companyId, applicationId);
        if (!application.getRecruitmentId().equals(recruitmentId)) {
            throw notFound();
        }
        if (application.getAnalysisStatus() != AnalysisStatus.FAILED) {
            throw new ApiException(HttpStatus.CONFLICT, "ANALYSIS_NOT_FAILED",
                    "Only a failed analysis can be retried.");
        }
        application.requestAnalysis();
        events.publishEvent(new ApplicationAnalysisRequested(applicationId, recruitmentId, companyId));
    }

    /** submittedBefore 전에 접수했는데 아직 분석 중인 지원서. 분석 작업을 잃었을 때 다시 맡기는 데 쓴다. */
    @Transactional(readOnly = true)
    public List<ApplicationAnalysisRequested> pendingAnalyses(Instant submittedBefore) {
        return applications.findByAnalysisStatusAndSubmittedAtBefore(AnalysisStatus.PENDING, submittedBefore).stream()
                .map(application -> new ApplicationAnalysisRequested(application.getId(),
                        application.getRecruitmentId(), application.getCompanyId()))
                .toList();
    }

    /** 분석에 넘길 제출 자료. 이벤트로 받은 지원서라 기업 범위 확인 없이 읽는다. */
    @Transactional(readOnly = true)
    public ApplicantDetail detailForAnalysis(UUID applicationId) {
        JobApplication application = applications.findById(applicationId).orElseThrow();
        return detail(application.getCompanyId(), applicationId);
    }

    @Transactional(readOnly = true)
    public FileContent documentContent(UUID companyId, UUID recruitmentId, UUID applicationId, DocumentType type) {
        JobApplication application = application(companyId, applicationId);
        if (!application.getRecruitmentId().equals(recruitmentId)) {
            throw notFound();
        }
        ApplicationDocument document = documents.findByApplicationId(applicationId).stream()
                .filter(candidate -> candidate.getType() == type)
                .findFirst()
                .orElseThrow(ApplicationService::notFound);
        return files.read(companyId, document.getFileId());
    }

    /** 블라인드 채용이면 본문의 학교 이름과 학점을 가려 저장한다. AI는 이 본문만 읽는다. 원본 PDF는 그대로 둔다. */
    private void saveDocument(JobApplication application, DocumentType type, ApplicationForm.Upload upload,
            boolean blind) {
        StoredFileInfo stored = files.storePdf(application.getCompanyId(), upload.fileName(), upload.content());
        String text = PdfText.extract(upload.content());
        documents.save(new ApplicationDocument(application.getId(), type, stored.fileId(), stored.originalName(),
                stored.size(), blind ? BlindMask.mask(text) : text));
    }

    private JobApplication application(UUID companyId, UUID applicationId) {
        return applications.findByIdAndCompanyId(applicationId, companyId).orElseThrow(ApplicationService::notFound);
    }

    private static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "APPLICATION_NOT_FOUND", "Application not found.");
    }

    /**
     * 블라인드 채용에서 마지막 전형 결과를 확정하기 전이면 HR · 면접관 화면과 AI에 지원자 이름 · 이메일 · 연락처를 주지 않는다.
     * 이름은 지원번호로 부르고, 서류 본문의 이름 · 이메일 · 전화번호도 가린다. 결과를 확정하면 최종 합격자 처리를 위해 보인다.
     */
    private boolean hidesIdentity(UUID companyId, UUID recruitmentId) {
        if (!postings.view(companyId, recruitmentId).content().blind()) {
            return false;
        }
        return recruits.get(companyId, recruitmentId).stages().stream()
                .max(Comparator.comparingInt(StageInfo::seq))
                .map(last -> last.status() != StageStatus.CONFIRMED && last.status() != StageStatus.DONE)
                .orElse(true);
    }

    /** 요청 하나 동안 채용별로 가릴지 한 번만 확인한다. */
    private final class Identity {

        private final UUID companyId;
        private final Map<UUID, Boolean> hidden = new HashMap<>();

        Identity(UUID companyId) {
            this.companyId = companyId;
        }

        boolean hides(JobApplication application) {
            return hidden.computeIfAbsent(application.getRecruitmentId(),
                    recruitmentId -> hidesIdentity(companyId, recruitmentId));
        }

        ApplicantInfo info(JobApplication application) {
            return toInfo(application, hides(application));
        }

        ApplicantDocument document(JobApplication application, ApplicationDocument document) {
            String text = hides(application) ? BlindMask.maskApplicant(document.getText(), application.getName())
                    : document.getText();
            return new ApplicantDocument(document.getType(), document.getFileId(), document.getFileName(),
                    document.getSizeBytes(), text);
        }
    }

    private static ApplicantInfo toInfo(JobApplication application, boolean hidden) {
        return new ApplicantInfo(application.getId(), application.getRecruitmentId(), application.getApplicationNo(),
                hidden ? ApplicantInfo.blindName(application.getApplicationNo()) : application.getName(),
                hidden ? "" : application.getEmail(), application.getCareerYears(),
                application.getLastCompany(), application.shortfalls(), application.getAnalysisStatus(),
                application.getSubmittedAt(), application.criterionMarks(), application.highTalents(),
                application.midTalents());
    }
}
