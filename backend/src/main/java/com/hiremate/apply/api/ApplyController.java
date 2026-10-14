package com.hiremate.apply.api;

import com.hiremate.apply.ApplicationForm;
import com.hiremate.apply.ApplicationPage;
import com.hiremate.apply.ApplicationService;
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

    public ApplyController(ApplicationService applications) {
        this.applications = applications;
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

    /** 접수 현황의 지원자 목록 (PST-03). */
    @GetMapping("/api/recruitments/{recruitmentId}/applications")
    public ApplicationPage list(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return applications.page(member.companyId(), recruitmentId, page, size);
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
