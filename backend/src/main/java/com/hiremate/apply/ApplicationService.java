package com.hiremate.apply;

import com.hiremate.apply.application.PdfText;
import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import com.hiremate.posting.ApplicationTarget;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.PostingService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
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

    public ApplicationService(JobApplicationRepository applications, ApplicationDocumentRepository documents,
            PostingService postings, FileService files, ApplicationEventPublisher events) {
        this.applications = applications;
        this.documents = documents;
        this.postings = postings;
        this.files = files;
        this.events = events;
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
        saveDocument(application, DocumentType.RESUME, form.resume());
        saveDocument(application, DocumentType.COVER_LETTER, form.coverLetter());
        if (form.portfolio() != null) {
            saveDocument(application, DocumentType.PORTFOLIO, form.portfolio());
        }
        events.publishEvent(new ApplicationSubmitted(application.getId(), target.recruitmentId(), target.companyId()));
        return new SubmittedApplication(application.getApplicationNo(), name, target.companyName(),
                target.postingTitle());
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
        return new ApplicationPage(found.getTotalElements(), found.stream()
                .map(application -> {
                    List<DocumentType> submitted = new ArrayList<>(types.getOrDefault(application.getId(), List.of()));
                    if (application.getCertificates() != null) {
                        submitted.add(DocumentType.CERTIFICATE);
                    }
                    submitted.sort(Comparator.naturalOrder());
                    return new ApplicationSummary(application.getId(), application.getApplicationNo(),
                            application.getName(), application.getSubmittedAt(), submitted);
                })
                .toList());
    }

    @Transactional(readOnly = true)
    public long count(UUID companyId, UUID recruitmentId) {
        return applications.countByRecruitmentIdAndCompanyId(recruitmentId, companyId);
    }

    @Transactional(readOnly = true)
    public List<ApplicantInfo> applicants(UUID companyId, UUID recruitmentId) {
        return applications.findByRecruitmentIdAndCompanyId(recruitmentId, companyId).stream()
                .map(ApplicationService::toInfo)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<ApplicantInfo> applicants(UUID companyId, List<UUID> applicationIds) {
        return applications.findByIdInAndCompanyId(applicationIds, companyId).stream()
                .map(ApplicationService::toInfo)
                .toList();
    }

    /** 채용 지원자 전원의 제출 문서. AI Chat이 후보의 근거를 찾을 때 쓴다. */
    @Transactional(readOnly = true)
    public Map<UUID, List<ApplicantDocument>> documents(UUID companyId, UUID recruitmentId) {
        List<UUID> ids = applications.findByRecruitmentIdAndCompanyId(recruitmentId, companyId).stream()
                .map(JobApplication::getId)
                .toList();
        return documents.findByApplicationIdIn(ids).stream()
                .sorted(Comparator.comparing(ApplicationDocument::getType))
                .collect(Collectors.groupingBy(ApplicationDocument::getApplicationId,
                        Collectors.mapping(document -> new ApplicantDocument(document.getType(), document.getFileId(),
                                document.getFileName(), document.getSizeBytes(), document.getText()),
                                Collectors.toList())));
    }

    /** 제출 문서 본문에 낱말이 들어 있는 지원서. */
    @Transactional(readOnly = true)
    public List<UUID> searchDocuments(UUID companyId, UUID recruitmentId, String keyword) {
        return documents.searchText(recruitmentId, companyId, keyword);
    }

    @Transactional(readOnly = true)
    public ApplicantDetail detail(UUID companyId, UUID applicationId) {
        JobApplication application = application(companyId, applicationId);
        return new ApplicantDetail(toInfo(application), application.getPhone(), application.getCertificates(),
                documents.findByApplicationId(applicationId).stream()
                        .sorted(Comparator.comparing(ApplicationDocument::getType))
                        .map(document -> new ApplicantDocument(document.getType(), document.getFileId(),
                                document.getFileName(), document.getSizeBytes(), document.getText()))
                        .toList());
    }

    /** 분석 Agent가 정리한 결과. 회사 범위 검증은 이벤트를 발행한 접수 단계에서 끝났다. */
    @Transactional
    public void recordAnalysis(UUID applicationId, ApplicationAnalysis analysis) {
        applications.findById(applicationId).ifPresent(application -> application.recordAnalysis(
                analysis.careerYears(), analysis.lastCompany(), analysis.documentScore(), analysis.passed()));
    }

    @Transactional
    public void markAnalysisFailed(UUID applicationId) {
        applications.findById(applicationId).ifPresent(JobApplication::markAnalysisFailed);
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

    private void saveDocument(JobApplication application, DocumentType type, ApplicationForm.Upload upload) {
        StoredFileInfo stored = files.storePdf(application.getCompanyId(), upload.fileName(), upload.content());
        documents.save(new ApplicationDocument(application.getId(), type, stored.fileId(), stored.originalName(),
                stored.size(), PdfText.extract(upload.content())));
    }

    private JobApplication application(UUID companyId, UUID applicationId) {
        return applications.findByIdAndCompanyId(applicationId, companyId).orElseThrow(ApplicationService::notFound);
    }

    private static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "APPLICATION_NOT_FOUND", "Application not found.");
    }

    private static ApplicantInfo toInfo(JobApplication application) {
        return new ApplicantInfo(application.getId(), application.getRecruitmentId(), application.getApplicationNo(),
                application.getName(), application.getEmail(), application.getCareerYears(),
                application.getLastCompany(), application.getDocumentScore(), application.isScorePassed(),
                application.getAnalysisStatus(), application.getSubmittedAt());
    }
}
