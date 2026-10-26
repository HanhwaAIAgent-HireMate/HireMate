package com.hiremate.company.api;

import com.hiremate.company.ReceiptTemplate;
import com.hiremate.company.ReceiptTemplateService;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.mail.MailPreview;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 설정 › 안내 메일의 접수 확인 메일 양식 API. 지원서를 내면 바로 가는 메일이라 AI는 쓰지 않는다. */
@RestController
@RequestMapping("/api/companies/me/receipt-template")
public class ReceiptTemplateController {

    private final ReceiptTemplateService templates;

    public ReceiptTemplateController(ReceiptTemplateService templates) {
        this.templates = templates;
    }

    @GetMapping
    public ReceiptTemplateView template(AuthenticatedMember member) {
        return ReceiptTemplateView.of(templates.template(member.companyId()));
    }

    @PutMapping
    public ReceiptTemplateView change(AuthenticatedMember member,
            @Valid @RequestBody ReceiptTemplateRequest request) {
        return ReceiptTemplateView.of(templates.change(member.companyId(),
                new ReceiptTemplate(request.subject().strip(), request.body().strip())));
    }

    /** 저장한 양식으로 만든 예시 메일. */
    @GetMapping("/preview")
    public MailPreview preview(AuthenticatedMember member) {
        return templates.preview(member.companyId());
    }

    /** 길이는 company_receipt_templates 테이블과 같다. */
    public record ReceiptTemplateRequest(@NotBlank @Size(max = 200) String subject,
            @NotBlank @Size(max = 5000) String body) {
    }

    /**
     * 접수 확인 메일 양식.
     *
     * @param requiredText 메일 바닥글로 붙는 필수 문구. 고칠 수 없다
     */
    public record ReceiptTemplateView(String subject, String body, String requiredText) {

        static ReceiptTemplateView of(ReceiptTemplate template) {
            return new ReceiptTemplateView(template.subject(), template.body(), ReceiptTemplate.REQUIRED_TEXT);
        }
    }
}
