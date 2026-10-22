package com.hiremate.apply.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.mail.MailService;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ReceiptTemplate;
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
        ApplicantDetail detail = applications.detailForAnalysis(event.applicationId());
        ReceiptTemplate receipt = postings.receiptMail(event.companyId(), event.recruitmentId(),
                detail.info().name(), detail.info().applicationNo());
        mail.send(detail.info().email(), receipt.subject(), receipt.body());
    }
}
