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
import com.hiremate.recruit.StageGuide;
import com.hiremate.recruit.StageInfo;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageResults;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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

    static final String GUIDE_LEAD = "일정과 준비 사항은 아래 안내를 확인해 주시기 바랍니다.";
    static final String ONBOARDING_LEAD = "입사 일정과 준비 사항은 아래 안내를 확인해 주시기 바랍니다.";
    static final String ONBOARDING_LATER = "입사 일정과 준비 사항은 담당자가 별도로 안내드릴 예정입니다.";

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
                .map(notice -> toView(notice, recruitment))
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
        return toView(notice, recruits.getByStage(companyId, stageId));
    }

    /**
     * HR이 확인한 초안을 지원자별 변수를 채워 보낸다. 이미 보낸 지원자는 건너뛰고, 실패한 지원자만 다시 보낼 수 있다.
     * 다음 전형 안내에는 보내는 때의 다음 전형 안내를 붙인다.
     */
    @Transactional
    public NoticeView send(UUID companyId, UUID stageId, NoticeGroup group, UUID memberId) {
        Notice notice = notice(companyId, stageId, group);
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        if (notice.isDone()) {
            return toView(notice, recruitment);
        }
        if (notice.getContent().isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICE_EMPTY", "Write the notice content first.");
        }
        StageResults results = screening.results(companyId, stageId);
        List<UUID> recipients = group == NoticeGroup.PASS ? results.passed() : results.failed();
        Map<UUID, NoticeDelivery> previous = deliveries.findByNoticeId(notice.getId()).stream()
                .collect(Collectors.toMap(NoticeDelivery::getApplicationId, Function.identity()));
        String stageName = recruitment.stage(stageId).orElseThrow().name();
        List<String> parts = new ArrayList<>(List.of(notice.getGreeting(), notice.getContent()));
        String guide = guideText(notice, recruitment);
        if (!guide.isEmpty()) {
            parts.add(guide);
        }
        parts.addAll(List.of(notice.getClosing(), notice.getRequiredText()));
        String body = String.join("\n\n", parts);
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
            MailResult result = mail.send(applicant.email(), fill(notice.getSubject(), values), fill(body, values));
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
        return toView(notice, recruitment);
    }

    /** 공고 작성 화면의 전형 안내. 첫 전형은 안내하는 메일이 없어 뺀다. */
    @Transactional(readOnly = true)
    public List<StageGuideView> guides(UUID companyId, UUID recruitmentId) {
        RecruitmentInfo recruitment = recruits.get(companyId, recruitmentId);
        return recruitment.stages().stream()
                .filter(stage -> stage.seq() > 1)
                .map(stage -> guideView(companyId, recruitment, stage))
                .toList();
    }

    /** 이미 보낸 메일은 바뀌지 않는다. 화면은 notifiedCount로 받은 사람이 있음을 알린다. */
    @Transactional
    public StageGuideView changeGuide(UUID companyId, UUID stageId, StageGuide guide) {
        StageInfo stage = recruits.changeGuide(companyId, stageId, guide);
        return guideView(companyId, recruits.getByStage(companyId, stageId), stage);
    }

    /** 최종 합격 안내의 입사 안내. 입사일은 최종 합격자를 정한 뒤에 정해져, 보내기 전 안내 화면에서 쓴다. */
    @Transactional
    public NoticeView changeOnboarding(UUID companyId, UUID stageId, NoticeGroup group, OnboardingGuide guide) {
        Notice notice = notice(companyId, stageId, group);
        if (notice.getTemplateType() != NoticeTemplateType.FINAL_PASS) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_FINAL_PASS",
                    "Only the final pass notice has an onboarding guide.");
        }
        if (!notice.isEditable()) {
            throw new ApiException(HttpStatus.CONFLICT, "NOTICE_SENT", "The notice has already been sent.");
        }
        notice.changeOnboarding(guide);
        return toView(notice, recruits.getByStage(companyId, stageId));
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

    /** 전형 안내와, 그 전형을 안내하는 메일(앞 전형의 다음 전형 안내)을 받은 지원자 수. */
    private StageGuideView guideView(UUID companyId, RecruitmentInfo recruitment, StageInfo stage) {
        int notified = recruitment.stages().stream()
                .filter(other -> other.seq() == stage.seq() - 1)
                .findFirst()
                .flatMap(before -> notices.findByStageIdAndCompanyIdAndGroupType(before.id(), companyId,
                        NoticeGroup.PASS))
                .map(Notice::getSentCount)
                .orElse(0);
        return new StageGuideView(stage.id(), stage.seq(), stage.name(), stage.guide(),
                missing(items(stage.guide())), notified);
    }

    /** 전형 안내 칸 이름과 값. 메일과 화면 경고에 같은 이름을 쓴다. 기타 안내(note)는 이름 없이 ※로 붙여 여기 없다. */
    private static Map<String, String> items(StageGuide guide) {
        Map<String, String> items = new LinkedHashMap<>();
        items.put("일정", guide.schedule());
        items.put("진행 방식", guide.method());
        items.put("장소·접속 링크", guide.place());
        items.put("준비 사항", guide.preparation());
        return items;
    }

    /** 입사 안내 칸 이름과 값. */
    private static Map<String, String> items(OnboardingGuide guide) {
        Map<String, String> items = new LinkedHashMap<>();
        items.put("입사일", guide.startDate());
        items.put("출근 장소", guide.place());
        items.put("제출 서류", guide.documents());
        items.put("준비 사항", guide.preparation());
        return items;
    }

    /** 비어 있는 안내 칸 이름. 게시하거나 안내를 보내기 전에 화면이 경고한다 (막지는 않는다). */
    private static List<String> missing(Map<String, String> items) {
        return items.entrySet().stream()
                .filter(item -> item.getValue().isEmpty())
                .map(Map.Entry::getKey)
                .toList();
    }

    /** 다음 전형 안내면 다음 전형. */
    private static Optional<StageInfo> nextStage(Notice notice, RecruitmentInfo recruitment) {
        if (notice.getTemplateType() != NoticeTemplateType.NEXT_STAGE) {
            return Optional.empty();
        }
        int seq = recruitment.stage(notice.getStageId()).orElseThrow().seq();
        return recruitment.stages().stream().filter(stage -> stage.seq() == seq + 1).findFirst();
    }

    /**
     * 본문 아래에 붙일 안내. 다음 전형 안내에는 다음 전형의 안내, 최종 합격 안내에는 입사 안내를 붙인다.
     * AI 본문과 따로 두어, 초안을 쓴 뒤에 안내를 고쳐도 다시 쓰지 않고 보내는 때의 안내가 붙는다.
     * 다음 전형 안내가 없으면 아무것도 붙이지 않고, 입사 안내가 없으면 담당자가 따로 안내한다고 쓴다.
     */
    static String guideText(Notice notice, RecruitmentInfo recruitment) {
        return switch (notice.getTemplateType()) {
            case NEXT_STAGE -> nextStage(notice, recruitment)
                    .filter(next -> next.guide().hasContent())
                    .map(next -> block(GUIDE_LEAD, next.name() + " 안내", items(next.guide()), next.guide().note()))
                    .orElse("");
            case FINAL_PASS -> notice.onboarding().hasContent()
                    ? block(ONBOARDING_LEAD, "입사 안내", items(notice.onboarding()), notice.onboarding().note())
                    : ONBOARDING_LATER;
            case REJECT, FINAL_REJECT -> "";
        };
    }

    /** 안내 묶음. 비어 있는 칸은 넣지 않고, 기타 안내는 이름 없이 한 줄마다 ※를 붙인다 ("기타 안내:"는 지원자에게 어색하다). */
    private static String block(String lead, String title, Map<String, String> items, String note) {
        List<String> lines = new ArrayList<>(List.of(lead, "", "■ " + title));
        items.forEach((label, value) -> {
            if (!value.isEmpty()) {
                lines.add("- " + label + ": " + value);
            }
        });
        List<String> notes = note.lines().map(String::strip).filter(line -> !line.isEmpty()).toList();
        if (!notes.isEmpty()) {
            lines.add("");
            notes.forEach(line -> lines.add("※ " + line));
        }
        return String.join("\n", lines);
    }

    /** 보내기 전에 화면이 경고할 비어 있는 안내 칸 이름. */
    private static List<String> guideMissing(Notice notice, RecruitmentInfo recruitment) {
        return switch (notice.getTemplateType()) {
            case NEXT_STAGE -> nextStage(notice, recruitment).map(next -> missing(items(next.guide())))
                    .orElse(List.of());
            case FINAL_PASS -> missing(items(notice.onboarding()));
            case REJECT, FINAL_REJECT -> List.of();
        };
    }

    private static NoticeView toView(Notice notice, RecruitmentInfo recruitment) {
        return new NoticeView(notice.getId(), notice.getStageId(), notice.getGroupType(), notice.getTemplateType(),
                label(notice.getTemplateType()), notice.getSubject(), notice.getGreeting(), notice.getContent(),
                guideText(notice, recruitment), guideMissing(notice, recruitment), notice.onboarding(),
                notice.getClosing(), notice.getRequiredText(), notice.getRecipientCount(), notice.getStatus(),
                notice.getSentCount(), notice.getFailedCount(), notice.getSentAt());
    }
}
