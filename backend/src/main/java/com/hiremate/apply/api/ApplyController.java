package com.hiremate.apply.api;

import com.hiremate.apply.ApplicationForm;
import com.hiremate.apply.ApplicationPage;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.DocumentNormalizationService;
import com.hiremate.apply.SchoolCheck;
import com.hiremate.apply.SubmittedApplication;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.DocumentType;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ApplyController {

    private final ApplicationService applications;

    private final DocumentNormalizationService normalization;

    public ApplyController(ApplicationService applications, DocumentNormalizationService normalization) {
        this.applications = applications;
        this.normalization = normalization;
    }

    /** 지원서 제출 (APL-02). 로그인 없이 쓰는 공개 API다. */
    @PostMapping(path = "/api/public/postings/{postingId}/applications",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public SubmittedApplication submit(@PathVariable UUID postingId, @RequestParam String name,
            @RequestParam String email, @RequestParam String phone,
            @RequestParam(required = false) String certificates, @RequestParam boolean consentPrivacy,
            @RequestParam boolean consentAi, @RequestPart MultipartFile resume, @RequestPart MultipartFile coverLetter,
            @RequestPart(required = false) MultipartFile portfolio) throws IOException {
        return applications.submit(postingId, new ApplicationForm(name, email, phone, certificates, consentPrivacy,
                consentAi, upload(resume), upload(coverLetter), upload(portfolio)));
    }

    /** 블라인드 채용 지원서의 학교 이름 확인. 제출 전에 지원자에게 알리고, 제출을 막지는 않는다. 로그인 없이 쓴다. */
    @PostMapping(path = "/api/public/postings/{postingId}/applications/school-check",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public SchoolCheck checkSchools(@PathVariable UUID postingId, @RequestPart MultipartFile resume,
            @RequestPart MultipartFile coverLetter, @RequestPart(required = false) MultipartFile portfolio)
            throws IOException {
        return applications.checkSchools(postingId, upload(resume), upload(coverLetter), upload(portfolio));
    }

    /** 접수 현황의 지원자 목록 (PST-03). */
    @GetMapping("/api/recruitments/{recruitmentId}/applications")
    public ApplicationPage list(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return applications.page(member.companyId(), recruitmentId, page, size);
    }

    /** 분석에 실패한 지원서를 다시 분석한다 (NFR-05). 결과는 분석이 끝나면 지원자 목록에 반영된다. */
    @PostMapping("/api/recruitments/{recruitmentId}/applications/{applicationId}/analysis")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void retryAnalysis(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @PathVariable UUID applicationId) {
        applications.retryAnalysis(member.companyId(), recruitmentId, applicationId);
    }

    @PostMapping("/api/recruitments/{recruitmentId}/applications/{applicationId}/documents/{documentId}/normalization")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void retryNormalization(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @PathVariable UUID applicationId, @PathVariable UUID documentId) {
        normalization.retry(member.companyId(), recruitmentId, applicationId, documentId);
    }

    /** 기존 지원 문서를 원본 PDF로 다시 읽는다. 반복 호출은 완료한 버전을 유지한다. */
    @PostMapping("/api/recruitments/{recruitmentId}/documents/normalization")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void backfillDocuments(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        normalization.backfill(member.companyId(), recruitmentId);
    }

    @GetMapping("/api/recruitments/{recruitmentId}/applications/{applicationId}/documents/{type}")
    public ResponseEntity<byte[]> document(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @PathVariable UUID applicationId, @PathVariable DocumentType type) {
        FileContent content = applications.documentContent(member.companyId(), recruitmentId, applicationId, type);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline()
                        .filename(content.info().originalName(), StandardCharsets.UTF_8).build().toString())
                .body(content.bytes());
    }

    private static ApplicationForm.Upload upload(MultipartFile file) throws IOException {
        return file == null || file.isEmpty() ? null : new ApplicationForm.Upload(file.getOriginalFilename(),
                file.getBytes());
    }
}
