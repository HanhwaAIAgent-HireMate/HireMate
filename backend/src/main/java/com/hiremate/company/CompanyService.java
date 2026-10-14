package com.hiremate.company;

import com.hiremate.company.application.DefaultNoticeTemplates;
import com.hiremate.company.domain.Company;
import com.hiremate.company.domain.CompanyFile;
import com.hiremate.company.domain.CompanyFileRepository;
import com.hiremate.company.domain.CompanyRepository;
import com.hiremate.company.domain.NoticeTemplate;
import com.hiremate.company.domain.NoticeTemplateRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 기업 정보와 설정(회사 소개 · 채용 공고 · 안내 메일). 다른 모듈은 조회 메서드로 설정을 가져간다. */
@Service
public class CompanyService {

    private final CompanyRepository companies;
    private final NoticeTemplateRepository noticeTemplates;
    private final CompanyFileRepository companyFiles;
    private final FileService files;

    public CompanyService(CompanyRepository companies, NoticeTemplateRepository noticeTemplates,
            CompanyFileRepository companyFiles, FileService files) {
        this.companies = companies;
        this.noticeTemplates = noticeTemplates;
        this.companyFiles = companyFiles;
        this.files = files;
    }

    @Transactional
    public CompanyInfo createCompany(String name) {
        Company company = companies.save(new Company(name));
        return new CompanyInfo(company.getId(), company.getName());
    }

    @Transactional(readOnly = true)
    public CompanyProfile profile(UUID companyId) {
        return toProfile(company(companyId));
    }

    @Transactional
    public CompanyProfile updateProfile(UUID companyId, String intro, String culture, List<Talent> talents,
            List<String> benefits) {
        Company company = company(companyId);
        company.updateProfile(intro, culture, talents, benefits);
        return toProfile(company);
    }

    @Transactional(readOnly = true)
    public PostingSettings postingSettings(UUID companyId) {
        Company company = company(companyId);
        return new PostingSettings(PostingSettings.SECTIONS, company.getWritingStyle(),
                List.copyOf(company.getRequiredNotices()));
    }

    @Transactional
    public PostingSettings updatePostingSettings(UUID companyId, String writingStyle, List<String> requiredNotices) {
        company(companyId).updatePostingSettings(writingStyle, requiredNotices);
        return postingSettings(companyId);
    }

    /** 네 가지 유형을 모두 돌려준다. 등록하지 않은 유형은 기본 양식이다. */
    @Transactional(readOnly = true)
    public List<NoticeTemplateInfo> noticeTemplates(UUID companyId) {
        Map<NoticeTemplateType, NoticeTemplateInfo> saved = noticeTemplates.findByCompanyId(companyId).stream()
                .map(NoticeTemplate::toInfo)
                .collect(Collectors.toMap(NoticeTemplateInfo::type, Function.identity()));
        return Arrays.stream(NoticeTemplateType.values())
                .map(type -> saved.getOrDefault(type, DefaultNoticeTemplates.of(type)))
                .toList();
    }

    @Transactional(readOnly = true)
    public NoticeTemplateInfo noticeTemplate(UUID companyId, NoticeTemplateType type) {
        return noticeTemplates.findByCompanyIdAndType(companyId, type)
                .map(NoticeTemplate::toInfo)
                .orElseGet(() -> DefaultNoticeTemplates.of(type));
    }

    @Transactional
    public NoticeTemplateInfo updateNoticeTemplate(UUID companyId, NoticeTemplateInfo info) {
        company(companyId);
        NoticeTemplate template = noticeTemplates.findByCompanyIdAndType(companyId, info.type())
                .orElseGet(() -> noticeTemplates.save(new NoticeTemplate(companyId, info)));
        template.update(info);
        return template.toInfo();
    }

    @Transactional(readOnly = true)
    public List<CompanyFileInfo> files(UUID companyId, CompanyFileCategory category) {
        return companyFiles.findByCompanyIdAndCategoryOrderByCreatedAt(companyId, category).stream()
                .map(CompanyService::toFileInfo)
                .toList();
    }

    @Transactional
    public CompanyFileInfo addFile(UUID companyId, CompanyFileCategory category, String name, byte[] content) {
        StoredFileInfo stored = files.storePdf(companyId, name, content);
        CompanyFile file = companyFiles.save(
                new CompanyFile(stored.fileId(), companyId, category, stored.originalName(), stored.size()));
        return toFileInfo(file);
    }

    @Transactional
    public void deleteFile(UUID companyId, UUID fileId) {
        companyFiles.delete(companyFile(companyId, fileId));
    }

    @Transactional(readOnly = true)
    public FileContent fileContent(UUID companyId, UUID fileId) {
        companyFile(companyId, fileId);
        return files.read(companyId, fileId);
    }

    private CompanyFile companyFile(UUID companyId, UUID fileId) {
        return companyFiles.findByFileIdAndCompanyId(fileId, companyId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "FILE_NOT_FOUND", "File not found."));
    }

    private Company company(UUID companyId) {
        return companies.findById(companyId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "COMPANY_NOT_FOUND", "Company not found."));
    }

    private static CompanyProfile toProfile(Company company) {
        return new CompanyProfile(company.getId(), company.getName(), company.getIntro(), company.getCulture(),
                List.copyOf(company.getTalents()), List.copyOf(company.getBenefits()));
    }

    private static CompanyFileInfo toFileInfo(CompanyFile file) {
        return new CompanyFileInfo(file.getFileId(), file.getCategory(), file.getName(), file.getSizeBytes(),
                file.getCreatedAt());
    }
}
