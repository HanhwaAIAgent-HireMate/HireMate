package com.hiremate.apply;

import com.hiremate.apply.domain.ApplicationDocument;
import com.hiremate.apply.domain.ApplicationDocumentRepository;
import com.hiremate.apply.domain.JobApplication;
import com.hiremate.apply.domain.JobApplicationRepository;
import com.hiremate.global.ApiException;
import com.hiremate.posting.BlindMask;
import com.hiremate.posting.DocumentType;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 지원 문서 정리 요청을 기업과 채용 범위 안에서 구성한다. */
@Service
public class DocumentNormalizationService {
    private final JobApplicationRepository applications;
    private final ApplicationDocumentRepository documents;
    private final ApplicationService applicationService;

    public DocumentNormalizationService(JobApplicationRepository applications,
            ApplicationDocumentRepository documents, ApplicationService applicationService) {
        this.applications = applications;
        this.documents = documents;
        this.applicationService = applicationService;
    }

    @Transactional(readOnly = true)
    public List<DocumentNormalizationRequest> requests(UUID companyId, UUID recruitmentId, UUID applicationId) {
        JobApplication application = applications.findByIdAndCompanyId(applicationId, companyId)
                .filter(candidate -> candidate.getRecruitmentId().equals(recruitmentId))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "APPLICATION_NOT_FOUND",
                        "Application not found."));
        boolean blind = applicationService.blind(companyId, recruitmentId);
        return documents.findByApplicationId(applicationId).stream()
                .filter(document -> document.getType() != DocumentType.CERTIFICATE)
                .filter(document -> document.getParsedDocument() != null)
                .map(document -> request(application, document, blind))
                .toList();
    }

    private static DocumentNormalizationRequest request(JobApplication application, ApplicationDocument document,
            boolean blind) {
        List<DocumentSource> sources = document.getParsedDocument().sources().stream()
                .map(source -> new DocumentSource(source.id(), source.page(), blind
                        ? BlindMask.maskApplicant(BlindMask.mask(source.text()), application.getName())
                        : source.text()))
                .toList();
        return new DocumentNormalizationRequest(application.getCompanyId(), application.getRecruitmentId(),
                application.getId(), document.getId(), document.getRevision(), document.getType(), sources);
    }
}
