package com.hiremate.notice;

import com.hiremate.activity.ActivityService;
import com.hiremate.apply.ApplicantContact;
import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.company.MailStyleService;
import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewScheduling;
import com.hiremate.interview.InterviewService;
import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailContent;
import com.hiremate.mail.MailPreview;
import com.hiremate.mail.MailResult;
import com.hiremate.mail.MailService;
import com.hiremate.notice.domain.Notice;
import com.hiremate.notice.domain.NoticeDelivery;
import com.hiremate.notice.domain.NoticeDeliveryRepository;
import com.hiremate.notice.domain.NoticeRepository;
import com.hiremate.recruit.GuideMethod;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageGuide;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageResults;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.regex.Pattern;
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
    static final String PREVIEW_APPLICANT = "홍길동";
    static final int PREVIEW_APPLICATION_NO = 1;
    /** 블라인드 채용 안내 메일의 맺음말 앞에 붙이는 지원번호 안내. */
    static final String APPLICATION_NO_LINE = "{지원자명}님의 지원번호는 {지원번호}번입니다.";
    /** 합격 안내를 보낼 수 있는 다음 면접 배정 상태. 다음 전형이 면접이 아니면 NOT_APPLICABLE이다. */
    private static final Set<String> SCHEDULED = Set.of("READY", "NOT_APPLICABLE");

    /** 전형 안내 일정을 오늘과 비교할 때 쓰는 시간대. */
    private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
    /** 온라인 전형의 접속 링크. 주소(호스트)가 있고 띄어쓰기가 없어야 한다. */
    private static final Pattern HTTP_URL = Pattern.compile("^https?://[^\\s/?#]+\\S*$", Pattern.CASE_INSENSITIVE);
    /** 메일에 쓰는 전형 일정 (예: 2026년 11월 3일(화)). */
    private static final DateTimeFormatter GUIDE_DATE = DateTimeFormatter.ofPattern("yyyy년 M월 d일(E)", Locale.KOREAN);
    private static final DateTimeFormatter GUIDE_TIME = DateTimeFormatter.ofPattern("HH:mm");
    /** 다음 면접 안내 메일의 지원자별 면접 일시. 보낼 때 지원자마다 채우는 안의 변수다. */
    private static final String INTERVIEW_TIME = "{면접일시}";
    /** 미리보기의 면접 일정 옆에 두는 메모. 실제 메일에는 지원자별 시각이 들어간다. */
    static final String PREVIEW_TIME_NOTE = "(시각은 지원자마다 배정된 시간으로 들어가요)";

    private final NoticeRepository notices;
    private final NoticeDeliveryRepository deliveries;
    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final CompanyService companies;
    private final MailStyleService mailStyles;
    private final MailService mail;
    private final ActivityService activity;
    private final InterviewScheduling scheduling;
    private final InterviewService interviews;

    public NoticeService(NoticeRepository notices, NoticeDeliveryRepository deliveries, ScreeningService screening,
            RecruitService recruits, ApplicationService applications, CompanyService companies,
            MailStyleService mailStyles, MailService mail, ActivityService activity, InterviewScheduling scheduling,
            InterviewService interviews) {
        this.notices = notices;
        this.deliveries = deliveries;
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.companies = companies;
        this.mailStyles = mailStyles;
        this.mail = mail;
        this.activity = activity;
        this.scheduling = scheduling;
        this.interviews = interviews;
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
        String companyName = companies.profile(companyId).name();
        // 다음 전형이 면접이면 안내의 일정 줄에 지원자마다 배정한 면접 일시를 넣는다
        Map<UUID, Instant> interviewTimes = interviewTimes(companyId, notice, recruitment);
        if (group == NoticeGroup.PASS) {
            // 이미 받은 지원자는 다시 보내지 않으므로, 이번에 보낼 지원자만 본다
            List<UUID> pending = recipients.stream()
                    .filter(id -> previous.get(id) == null || !previous.get(id).isSent())
                    .toList();
            requireInterviewTimes(companyId, stageId, pending, interviewTimes);
        }
        MailContent content = content(notice, recruitment, companyName, !interviewTimes.isEmpty(),
                applications.blind(companyId, recruitment.id()));
        MailBrand brand = mailStyles.brand(companyId);
        int sent = 0;
        int failed = 0;
        // 블라인드 채용에서도 지원자 본인에게 보내는 메일이라 실제 이름과 이메일을 쓴다
        for (ApplicantContact applicant : applications.contacts(companyId, recipients)) {
            NoticeDelivery delivery = previous.get(applicant.applicationId());
            if (delivery != null && delivery.isSent()) {
                sent++;
                continue;
            }
            Instant interviewAt = interviewTimes.get(applicant.applicationId());
            Map<String, String> values = new HashMap<>(values(applicant.name(), applicant.applicationNo(), companyName,
                    recruitment, stageId));
            values.put(INTERVIEW_TIME, interviewAt == null ? "" : formatInterview(interviewAt));
            MailResult result = mail.send(applicant.email(), fill(notice.getSubject(), values),
                    content.fill(values), brand);
            if (delivery == null) {
                delivery = deliveries.save(new NoticeDelivery(notice.getId(), applicant.applicationId(),
                        applicant.email()));
            }
            delivery.result(result.sent(), result.error(), interviewAt);
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

    /** 보내기 전 화면의 미리보기. 저장한 초안으로 보낼 때와 같은 메일을 만들고, 지원자 이름은 예시로 채운다. */
    @Transactional(readOnly = true)
    public MailPreview preview(UUID companyId, UUID stageId, NoticeGroup group) {
        Notice notice = notice(companyId, stageId, group);
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        String companyName = companies.profile(companyId).name();
        Map<String, String> values = new HashMap<>(values(PREVIEW_APPLICANT, PREVIEW_APPLICATION_NO, companyName,
                recruitment, stageId));
        Optional<String> interviewTime = previewInterviewTime(notice, recruitment);
        interviewTime.ifPresent(time -> values.put(INTERVIEW_TIME, time));
        return MailPreview.of(fill(notice.getSubject(), values),
                content(notice, recruitment, companyName, interviewTime.isPresent(),
                        applications.blind(companyId, recruitment.id())).fill(values),
                mailStyles.brand(companyId));
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

    /**
     * 안내 메일을 받은 지원자가 있으면 고칠 수 없다. 이미 보낸 메일은 바뀌지 않으므로, 바뀐 내용은 HR이 따로 연락하고
     * 시스템에는 지원자가 받은 안내를 그대로 둔다. 다시 보내는 지원자도 같은 안내를 받는다.
     */
    @Transactional
    public StageGuideView changeGuide(UUID companyId, UUID stageId, StageGuide guide) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        if (guideView(companyId, recruitment, stage).notifiedCount() > 0) {
            throw new ApiException(HttpStatus.CONFLICT, "GUIDE_LOCKED", "The guide was already sent to applicants.");
        }
        checkGuide(recruitment, stage, guide);
        scheduling.guideChanged(companyId, stageId, guide.schedule(), true);
        StageInfo changed = recruits.changeGuide(companyId, stageId, guide);
        return guideView(companyId, recruits.getByStage(companyId, stageId), changed);
    }

    /**
     * 맞지 않는 안내는 저장하지 않는다. 일정은 바꿀 때만 오늘 이후인지 본다(이미 지난 전형의 안내도 고칠 수 있게).
     * 일정은 앞 전형보다 뒤 · 다음 전형보다 앞이어야 한다(일정을 정한 가장 가까운 전형과 비교한다).
     * 장소는 진행 방식을 정한 뒤에 쓰고, 온라인이면 http · https 주소, 오프라인이면 꼭 쓴다.
     */
    private static void checkGuide(RecruitmentInfo recruitment, StageInfo stage, StageGuide guide) {
        LocalDate date = guide.schedule();
        if (date != null && !date.equals(stage.guide().schedule()) && date.isBefore(LocalDate.now(KOREA))) {
            throw invalidGuide("GUIDE_DATE_PAST", "The schedule is in the past.");
        }
        // 오늘로 정한 시작 시각은 지금보다 뒤여야 한다. 바꾸지 않은 일정 · 시각은 그대로 둘 수 있다
        boolean changed = !Objects.equals(date, stage.guide().schedule()) || !Objects.equals(guide.time(),
                stage.guide().time());
        if (changed && guide.time() != null && stage.type() != StageType.INTERVIEW
                && LocalDate.now(KOREA).equals(date) && !guide.time().isAfter(LocalTime.now(KOREA))) {
            throw invalidGuide("GUIDE_DATE_PAST", "The schedule is in the past.");
        }
        if (date != null && recruitment.stages().stream().anyMatch(other -> other.guide().schedule() != null
                && (other.seq() < stage.seq() ? !other.guide().schedule().isBefore(date)
                        : other.seq() > stage.seq() && !other.guide().schedule().isAfter(date)))) {
            throw invalidGuide("GUIDE_DATE_ORDER", "The schedule must be between the previous and next stages.");
        }
        String place = guide.place();
        if (guide.method() == null && !place.isEmpty()) {
            throw invalidGuide("GUIDE_METHOD_REQUIRED", "Choose the method before the place.");
        }
        if (guide.method() == GuideMethod.OFFLINE && place.isEmpty()) {
            throw invalidGuide("GUIDE_PLACE_REQUIRED", "An offline stage needs a place.");
        }
        if (guide.method() == GuideMethod.ONLINE && !place.isEmpty() && !HTTP_URL.matcher(place).matches()) {
            throw invalidGuide("GUIDE_LINK_INVALID", "An online stage needs an http or https link.");
        }
    }

    private static ApiException invalidGuide(String code, String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, code, message);
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

    /**
     * 메일 내용. 인사말과 본문, 붙일 안내, 맺음말, 필수 문구 순서다. 변수는 아직 채우지 않았다. interviewTime이면 다음 전형
     * 안내의 일정 줄을 지원자별 면접 일시 변수로 둔다. 블라인드 채용이면 맺음말 앞에 지원자 본인의 지원번호를 알린다. 담당자
     * 화면에는 이름 대신 지원번호가 보여 지원자가 문의할 때 번호가 필요하다.
     */
    private static MailContent content(Notice notice, RecruitmentInfo recruitment, String companyName,
            boolean interviewTime, boolean blind) {
        List<MailContent.Block> blocks = new ArrayList<>(List.of(new MailContent.Text(notice.getGreeting()),
                new MailContent.Text(notice.getContent())));
        guideBlock(notice, recruitment, interviewTime).ifPresent(blocks::add);
        if (blind) {
            blocks.add(new MailContent.Text(APPLICATION_NO_LINE));
        }
        return new MailContent(companyName, recruitment.title(), blocks, notice.getClosing(),
                notice.getRequiredText());
    }

    /** {지원번호}는 블라인드 채용에서 면접관이 지원자를 번호로 부르므로, 지원자가 자기 번호를 알 수 있게 쓴다. */
    private static Map<String, String> values(String applicantName, int applicationNo, String companyName,
            RecruitmentInfo recruitment, UUID stageId) {
        return Map.of("{지원자명}", applicantName, "{지원번호}", String.valueOf(applicationNo), "{회사명}", companyName,
                "{공고명}", recruitment.title(), "{전형명}", recruitment.stage(stageId).orElseThrow().name());
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
        return new StageGuideView(stage.id(), stage.seq(), stage.name(), stage.type(), stage.guide(),
                missing(items(stage.guide())), notified);
    }

    /**
     * 면접 전형(stageId)의 지원자별로, 앞 전형의 합격 안내 메일에 안내한 면접 일시. 아직 보내지 않았거나 면접 일시 없이 보낸
     * 지원자는 빠진다. 면접 화면이 지금 일정과 비교해 발송 뒤 바뀐 일정을 알린다.
     */
    @Transactional(readOnly = true)
    public List<NotifiedInterview> notifiedInterviews(UUID companyId, UUID stageId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        int seq = recruitment.stage(stageId).orElseThrow().seq();
        return recruitment.stages().stream()
                .filter(before -> before.seq() == seq - 1)
                .findFirst()
                .flatMap(before -> notices.findByStageIdAndCompanyIdAndGroupType(before.id(), companyId,
                        NoticeGroup.PASS))
                .map(pass -> deliveries.findByNoticeId(pass.getId()).stream()
                        .filter(delivery -> delivery.isSent() && delivery.getInterviewAt() != null)
                        .map(delivery -> new NotifiedInterview(delivery.getApplicationId(), delivery.getInterviewAt(),
                                delivery.getSentAt()))
                        .toList())
                .orElse(List.of());
    }

    /**
     * 다음 전형이 면접이면 면접 시간을 배정한 뒤에 합격 안내를 보낸다. 배정을 마쳤어도 이번에 보낼 합격자 가운데 면접 일시가
     * 비어 있는 지원자가 있으면 보내지 않는다 (시간이 빠진 메일이 나가면 안 된다). 보내면 다음 전형 안내가 잠긴다.
     */
    private void requireInterviewTimes(UUID companyId, UUID stageId, List<UUID> recipients,
            Map<UUID, Instant> interviewTimes) {
        InterviewScheduling.Status status = scheduling.status(companyId, stageId);
        if (!SCHEDULED.contains(status.status())) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_NOT_READY",
                    "Schedule the next interview before sending the pass notice.");
        }
        if (status.nextStageId() == null) {
            return;
        }
        long missing = recipients.stream().filter(id -> !interviewTimes.containsKey(id)).count();
        if (missing > 0) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_TIME_MISSING",
                    missing + " applicants have no interview time.");
        }
    }

    /** 다음 면접 전형에 지원자마다 배정한 면접 일시. 다음 전형이 면접이 아니거나 합격 안내가 아니면 비어 있다. */
    private Map<UUID, Instant> interviewTimes(UUID companyId, Notice notice, RecruitmentInfo recruitment) {
        return nextStage(notice, recruitment)
                .filter(next -> notice.getGroupType() == NoticeGroup.PASS && next.type() == StageType.INTERVIEW)
                .map(next -> interviews.schedules(companyId, next.id()).stream()
                        .collect(Collectors.toMap(InterviewService.StageSchedule::applicationId,
                                InterviewService.StageSchedule::scheduledAt)))
                .orElse(Map.of());
    }

    /** 미리보기의 면접 일시. 시각은 지원자마다 달라, 날짜 옆에 보낼 때 지원자별 시각이 들어간다고 적는다. */
    private static Optional<String> previewInterviewTime(Notice notice, RecruitmentInfo recruitment) {
        return nextStage(notice, recruitment)
                .filter(next -> notice.getGroupType() == NoticeGroup.PASS && next.type() == StageType.INTERVIEW)
                .map(next -> (next.guide().schedule() == null ? "" : GUIDE_DATE.format(next.guide().schedule()) + " ")
                        + PREVIEW_TIME_NOTE);
    }

    /** 일정 줄을 지원자별 면접 일시 변수로 바꾼 안내 칸. */
    private static Map<String, String> withInterviewTime(Map<String, String> items) {
        Map<String, String> replaced = new LinkedHashMap<>(items);
        replaced.put("일정", INTERVIEW_TIME);
        return replaced;
    }

    /** 메일에 쓰는 면접 일시 (예: 2026년 11월 12일(목) 14:00). */
    static String formatInterview(Instant at) {
        ZonedDateTime local = at.atZone(KOREA);
        return GUIDE_DATE.format(local) + " " + GUIDE_TIME.format(local);
    }

    /** 전형 안내 칸 이름과 값. 메일과 화면 경고에 같은 이름을 쓴다. 기타 안내(note)는 이름 없이 ※로 붙여 여기 없다. */
    private static Map<String, String> items(StageGuide guide) {
        Map<String, String> items = new LinkedHashMap<>();
        String time = guide.time() == null ? "" : " " + GUIDE_TIME.format(guide.time());
        items.put("일정", guide.schedule() == null ? "" : GUIDE_DATE.format(guide.schedule()) + time);
        items.put("진행 방식", guide.method() == null ? "" : guide.method().label());
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
        return guideBlock(notice, recruitment, false).map(MailContent.Block::text).orElse("");
    }

    /** guideText의 메일 블록. 안내가 있으면 안내 상자, 입사 안내가 없으면 따로 안내한다는 문장이다. */
    private static Optional<MailContent.Block> guideBlock(Notice notice, RecruitmentInfo recruitment,
            boolean interviewTime) {
        return switch (notice.getTemplateType()) {
            case NEXT_STAGE -> nextStage(notice, recruitment)
                    .filter(next -> next.guide().hasContent())
                    .map(next -> guide(GUIDE_LEAD, next.name() + " 안내", interviewTime
                            ? withInterviewTime(items(next.guide())) : items(next.guide()), next.guide().note()));
            case FINAL_PASS -> Optional.of(notice.onboarding().hasContent()
                    ? guide(ONBOARDING_LEAD, "입사 안내", items(notice.onboarding()), notice.onboarding().note())
                    : new MailContent.Text(ONBOARDING_LATER));
            case REJECT, FINAL_REJECT -> Optional.empty();
        };
    }

    /** 안내 상자. 비어 있는 칸은 넣지 않고, 기타 안내는 이름 없이 한 줄마다 ※를 붙인다 ("기타 안내:"는 지원자에게 어색하다). */
    private static MailContent.Guide guide(String lead, String title, Map<String, String> items, String note) {
        List<MailContent.Item> filled = items.entrySet().stream()
                .filter(item -> !item.getValue().isEmpty())
                .map(item -> new MailContent.Item(item.getKey(), item.getValue()))
                .toList();
        List<String> notes = note.lines().map(String::strip).filter(line -> !line.isEmpty()).toList();
        return new MailContent.Guide(lead, title, filled, notes);
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
