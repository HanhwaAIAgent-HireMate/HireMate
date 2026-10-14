package com.hiremate.notice;

import com.hiremate.activity.ActivityService;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;
import com.hiremate.global.ApiException;
import com.hiremate.mail.MailResult;
import com.hiremate.mail.MailService;
import com.hiremate.notice.domain.Notice;
import com.hiremate.notice.domain.NoticeDelivery;
import com.hiremate.notice.domain.NoticeDeliveryRepository;
import com.hiremate.notice.domain.NoticeRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageResults;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 전형 결과 안내 (FR-29). 확정 결과로 그룹별 초안을 만들고, HR이 확인한 뒤 발송한다. AI는 발송하지 않는다.
 */
@Service
public class NoticeService {

    private final NoticeRepository notices;
    private final NoticeDeliveryRepository deliveries;
    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final CompanyService companies;
    private final MailService mail;
    private final ActivityService activity;

    public NoticeService(NoticeRepository notices, NoticeDeliveryRepository deliveries, ScreeningService screening,
            RecruitService recruits, ApplicationService applications, CompanyService companies, MailService mail,
            ActivityService activity) {
        this.notices = notices;
        this.deliveries = deliveries;
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.companies = companies;
        this.mail = mail;
        this.activity = activity;
    }

    /** 결과를 확정한 전형의 안내 초안. 처음 열면 설정의 안내 메일 양식으로 그룹별 초안을 만든다. */
    @Transactional
    public List<NoticeView> notices(UUID companyId, UUID stageId) {
        StageResults results = screening.results(companyId, stageId);
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        boolean last = recruitment.isLastStage(stageId);
        ensure(companyId, recruitment, stageId, NoticeGroup.PASS,
                last ? NoticeTemplateType.FINAL_PASS : NoticeTemplateType.NEXT_STAGE, results.passed().size());
        ensure(companyId, recruitment, stageId, NoticeGroup.FAIL,
                last ? NoticeTemplateType.FINAL_REJECT : NoticeTemplateType.REJECT, results.failed().size());
        return notices.findByStageIdAndCompanyIdOrderByGroupTypeDesc(stageId, companyId).stream()
                .map(NoticeService::toView)
                .toList();
    }

    /** Communication Agent에 넘길 정보. */
    @Transactional
    public NoticeDraftContext draftContext(UUID companyId, UUID stageId, NoticeGroup group) {
        notices(companyId, stageId);
        Notice notice = notice(companyId, stageId, group);
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        String next = recruitment.stages().stream().filter(other -> other.seq() == stage.seq() + 1)
                .map(StageInfo::name).findFirst().orElse(null);
        NoticeTemplateInfo template = companies.noticeTemplate(companyId, notice.getTemplateType());
        return new NoticeDraftContext(notice.getId(), notice.getTemplateType(), companies.profile(companyId).name(),
                recruitment.title(), stage.name(), next, template.aiGuide(), notice.getContent());
    }

    /** HR이 초안을 직접 고치거나 AI 수정안을 적용한다. 필수 문구는 바꿀 수 없다. */
    @Transactional
    public NoticeView edit(UUID companyId, UUID stageId, NoticeGroup group, String subject, String greeting,
            String content, String closing) {
        Notice notice = notice(companyId, stageId, group);
        if (!notice.isEditable()) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICE_SENT", "The notice has already been sent.");
        }
        notice.edit(subject, greeting, content, closing);
        return toView(notice);
    }

    /**
     * HR이 확인한 초안을 지원자별 변수를 채워 보낸다. 이미 보낸 지원자는 건너뛰고, 실패한 지원자만 다시 보낼 수 있다.
     */
    @Transactional
    public NoticeView send(UUID companyId, UUID stageId, NoticeGroup group, UUID memberId) {
        Notice notice = notice(companyId, stageId, group);
        if (notice.isDone()) {
            return toView(notice);
        }
        if (notice.getContent().isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICE_EMPTY", "Write the notice content first.");
        }
        StageResults results = screening.results(companyId, stageId);
        List<UUID> recipients = group == NoticeGroup.PASS ? results.passed() : results.failed();
        Map<UUID, NoticeDelivery> previous = deliveries.findByNoticeId(notice.getId()).stream()
                .collect(Collectors.toMap(NoticeDelivery::getApplicationId, Function.identity()));
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        String stageName = recruitment.stage(stageId).orElseThrow().name();
        String companyName = companies.profile(companyId).name();
        int sent = 0;
        int failed = 0;
        for (ApplicantInfo applicant : applications.applicants(companyId, recipients)) {
            NoticeDelivery delivery = previous.get(applicant.applicationId());
            if (delivery != null && delivery.isSent()) {
                sent++;
                continue;
            }
            Map<String, String> values = Map.of("{지원자명}", applicant.name(), "{회사명}", companyName,
                    "{공고명}", recruitment.title(), "{전형명}", stageName);
            MailResult result = mail.send(applicant.email(), fill(notice.getSubject(), values),
                    fill(String.join("\n\n", notice.getGreeting(), notice.getContent(), notice.getClosing(),
                            notice.getRequiredText()), values));
            if (delivery == null) {
                delivery = deliveries.save(new NoticeDelivery(notice.getId(), applicant.applicationId(),
                        applicant.email()));
            }
            delivery.result(result.sent(), result.error());
            if (result.sent()) {
                sent++;
            } else {
                failed++;
            }
        }
        notice.recordSending(sent, failed, memberId);
        activity.record(companyId, memberId, "SEND_NOTICE", "STAGE", stageId,
                group + " sent=" + sent + ", failed=" + failed);
        return toView(notice);
    }

    /** 모든 그룹의 안내를 보냈는지. 전형 종료 전에 확인한다. */
    @Transactional
    public boolean allSent(UUID companyId, UUID stageId) {
        return notices(companyId, stageId).stream()
                .allMatch(view -> view.status() == NoticeStatus.SENT || view.status() == NoticeStatus.EMPTY);
    }

    private void ensure(UUID companyId, RecruitmentInfo recruitment, UUID stageId, NoticeGroup group,
            NoticeTemplateType type, int recipients) {
        if (notices.findByStageIdAndCompanyIdAndGroupType(stageId, companyId, group).isPresent()) {
            return;
        }
        NoticeTemplateInfo template = companies.noticeTemplate(companyId, type);
        notices.save(new Notice(stageId, recruitment.id(), companyId, group, type, template.subject(),
                template.greeting(), template.closing(), template.requiredText(), recipients));
    }

    private Notice notice(UUID companyId, UUID stageId, NoticeGroup group) {
        return notices.findByStageIdAndCompanyIdAndGroupType(stageId, companyId, group).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "NOTICE_NOT_FOUND", "Notice not found."));
    }

    private static String fill(String text, Map<String, String> values) {
        String filled = text;
        for (Map.Entry<String, String> entry : values.entrySet()) {
            filled = filled.replace(entry.getKey(), entry.getValue());
        }
        return filled;
    }

    static String label(NoticeTemplateType type) {
        return switch (type) {
            case NEXT_STAGE -> "다음 전형 안내";
            case REJECT, FINAL_REJECT -> "불합격 안내";
            case FINAL_PASS -> "최종 합격 안내";
        };
    }

    private static NoticeView toView(Notice notice) {
        return new NoticeView(notice.getId(), notice.getStageId(), notice.getGroupType(), notice.getTemplateType(),
                label(notice.getTemplateType()), notice.getSubject(), notice.getGreeting(), notice.getContent(),
                notice.getClosing(), notice.getRequiredText(), notice.getRecipientCount(), notice.getStatus(),
                notice.getSentCount(), notice.getFailedCount(), notice.getSentAt());
    }
}
