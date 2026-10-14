package com.hiremate.apply.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.mail.MailService;
import com.hiremate.recruit.RecruitService;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 접수가 끝나면 지원자에게 접수 확인 메일을 보낸다. 발송 실패는 접수 결과에 영향을 주지 않는다. */
@Component
class ConfirmationMailer {

    private final ApplicationService applications;
    private final RecruitService recruits;
    private final MailService mail;

    ConfirmationMailer(ApplicationService applications, RecruitService recruits, MailService mail) {
        this.applications = applications;
        this.recruits = recruits;
        this.mail = mail;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        ApplicantDetail detail = applications.detailForAnalysis(event.applicationId());
        String title = recruits.get(event.companyId(), event.recruitmentId()).title();
        mail.send(detail.info().email(), "[" + title + "] 지원이 접수됐어요",
                detail.info().name() + "님, " + title + " 채용에 지원해 주셔서 감사합니다.\n\n"
                        + "지원번호 " + detail.info().applicationNo() + "번으로 접수했어요. "
                        + "전형 결과는 이 메일 주소로 안내드릴게요.\n\n본 메일은 발신 전용입니다.");
    }
}
