package com.hiremate.company;

import com.hiremate.company.domain.CompanyReceiptTemplate;
import com.hiremate.company.domain.CompanyReceiptTemplateRepository;
import com.hiremate.mail.MailPreview;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 접수 확인 메일 양식. 설정 › 안내 메일에서 고치고, 지원서를 내면 공고 모듈이 그때의 양식으로 보낸다. */
@Service
public class ReceiptTemplateService {

    static final String PREVIEW_TITLE = "예시 공고";

    private final CompanyReceiptTemplateRepository templates;
    private final CompanyService companies;
    private final MailStyleService mailStyles;

    public ReceiptTemplateService(CompanyReceiptTemplateRepository templates, CompanyService companies,
            MailStyleService mailStyles) {
        this.templates = templates;
        this.companies = companies;
        this.mailStyles = mailStyles;
    }

    @Transactional(readOnly = true)
    public ReceiptTemplate template(UUID companyId) {
        return templates.findById(companyId)
                .map(saved -> new ReceiptTemplate(saved.getSubject(), saved.getBody()))
                .orElse(ReceiptTemplate.DEFAULT);
    }

    @Transactional
    public ReceiptTemplate change(UUID companyId, ReceiptTemplate template) {
        templates.findById(companyId).ifPresentOrElse(saved -> saved.change(template.subject(), template.body()),
                () -> templates.save(new CompanyReceiptTemplate(companyId, template.subject(), template.body())));
        return template;
    }

    /**
     * 설정 화면의 미리보기. 저장한 양식으로 만들고, 공고명과 지원자 값은 예시다. 트랜잭션 없이 조회 메서드를 부른다.
     *
     * @param look 메일 꾸밈에서 고르는 중인 색과 부품. null이면 저장한 꾸밈이다
     */
    public MailPreview preview(UUID companyId, MailLook look) {
        String companyName = companies.profile(companyId).name();
        ReceiptTemplate filled = template(companyId).fill(companyName, PREVIEW_TITLE, "홍길동", 1);
        return MailPreview.of(filled.subject(), filled.toMail(companyName, PREVIEW_TITLE),
                mailStyles.brand(companyId, look));
    }
}
