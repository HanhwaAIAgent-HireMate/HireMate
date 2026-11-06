package com.hiremate.apply.application;

import com.hiremate.apply.ApplicantContact;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.mail.MailService;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ReceiptMail;
import java.util.List;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/**
 * 접수가 끝나면 지원자에게 접수 확인 메일을 보낸다. 문장은 HR이 공고를 쓸 때 확인한 공고의 템플릿이다.
 * 발송 실패는 접수 결과에 영향을 주지 않는다.
 */
@Component
class ConfirmationMailer {

    private final ApplicationService applications;
    private final PostingService postings;
    private final MailService mail;

    ConfirmationMailer(ApplicationService applications, PostingService postings, MailService mail) {
        this.applications = applications;
        this.postings = postings;
        this.mail = mail;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        // 블라인드 채용에서도 지원자 본인에게 보내는 메일이라 실제 이름과 이메일을 쓴다
        ApplicantContact contact = applications.contacts(event.companyId(), List.of(event.applicationId()))
                .getFirst();
        ReceiptMail receipt = postings.receiptMail(event.companyId(), event.recruitmentId(), contact.name(),
                contact.applicationNo());
        mail.send(contact.email(), receipt.subject(), receipt.content(), receipt.brand());
    }
}
