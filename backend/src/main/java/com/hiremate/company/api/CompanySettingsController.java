package com.hiremate.company.api;

import com.hiremate.company.CompanyFileCategory;
import com.hiremate.company.CompanyFileInfo;
import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;
import com.hiremate.company.PostingSettings;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import jakarta.validation.Valid;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 설정 화면(회사 소개 · 채용 공고 · 안내 메일) API. 로그인한 HR의 기업만 다룬다. */
@RestController
@RequestMapping("/api/companies/me")
public class CompanySettingsController {

    private final CompanyService companies;

    public CompanySettingsController(CompanyService companies) {
        this.companies = companies;
    }

    @GetMapping("/profile")
    public CompanyProfile profile(AuthenticatedMember member) {
        return companies.profile(member.companyId());
    }

    @PutMapping("/profile")
    public CompanyProfile updateProfile(AuthenticatedMember member, @Valid @RequestBody ProfileRequest request) {
        return companies.updateProfile(member.companyId(), request.intro(), request.culture(), request.talentList(),
                request.benefits(), request.addressText());
    }

    @GetMapping("/posting-settings")
    public PostingSettings postingSettings(AuthenticatedMember member) {
        return companies.postingSettings(member.companyId());
    }

    @PutMapping("/posting-settings")
    public PostingSettings updatePostingSettings(AuthenticatedMember member,
            @Valid @RequestBody PostingSettingsRequest request) {
        return companies.updatePostingSettings(member.companyId(), request.writingStyle(), request.requiredNotices());
    }

    @GetMapping("/notice-templates")
    public List<NoticeTemplateInfo> noticeTemplates(AuthenticatedMember member) {
        return companies.noticeTemplates(member.companyId());
    }

    @PutMapping("/notice-templates/{type}")
    public NoticeTemplateInfo updateNoticeTemplate(AuthenticatedMember member, @PathVariable NoticeTemplateType type,
            @Valid @RequestBody NoticeTemplateRequest request) {
        return companies.updateNoticeTemplate(member.companyId(), request.toInfo(type));
    }

    @GetMapping("/files")
    public List<CompanyFileInfo> files(AuthenticatedMember member, @RequestParam CompanyFileCategory category) {
        return companies.files(member.companyId(), category);
    }

    @PostMapping(path = "/files", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public CompanyFileInfo uploadFile(AuthenticatedMember member, @RequestParam CompanyFileCategory category,
            @RequestPart("file") MultipartFile file) throws IOException {
        return companies.addFile(member.companyId(), category, file.getOriginalFilename(), file.getBytes());
    }

    @DeleteMapping("/files/{fileId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteFile(AuthenticatedMember member, @PathVariable UUID fileId) {
        companies.deleteFile(member.companyId(), fileId);
    }

    @GetMapping("/files/{fileId}/content")
    public ResponseEntity<byte[]> fileContent(AuthenticatedMember member, @PathVariable UUID fileId) {
        FileContent content = companies.fileContent(member.companyId(), fileId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline()
                        .filename(content.info().originalName(), StandardCharsets.UTF_8).build().toString())
                .body(content.bytes());
    }
}
