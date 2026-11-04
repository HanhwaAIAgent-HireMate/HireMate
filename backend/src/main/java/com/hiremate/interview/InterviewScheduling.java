package com.hiremate.interview;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.interview.domain.InterviewSchedulingJob;
import com.hiremate.interview.domain.InterviewSchedulingJobRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 결과 확정과 안내 날짜 저장 뒤 면접 일정을 배정한다. 직접 수정한 시간은 보존한다. */
@Service
public class InterviewScheduling {

    private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
    /** 평일 하루 아홉 칸의 시작 시각. 한 칸은 한 시간이라 마지막 칸은 18시에 끝난다 */
    private static final List<Integer> HOURS = List.of(9, 10, 11, 12, 13, 14, 15, 16, 17);

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationService applications;
    private final InterviewScheduleRepository schedules;
    private final ApplicationEventPublisher events;
    private final InterviewSchedulingJobRepository jobs;
    private final InterviewSessionRepository sessions;
    private final InterviewAttendanceRepository attendance;

    public InterviewScheduling(RecruitService recruits, ScreeningService screening, ApplicationService applications,
            InterviewScheduleRepository schedules, ApplicationEventPublisher events,
            InterviewSchedulingJobRepository jobs, InterviewSessionRepository sessions,
            InterviewAttendanceRepository attendance) {
        this.recruits = recruits;
        this.screening = screening;
        this.applications = applications;
        this.schedules = schedules;
        this.events = events;
        this.jobs = jobs;
        this.sessions = sessions;
        this.attendance = attendance;
    }

    /**
     * 안내 날짜를 저장하기 전에 부른다. 배정 작업과 같은 앞 전형 잠금을 먼저 잡고, 저장이 커밋된 뒤 배정한다.
     * allowReassignment는 안내 담당 모듈이 합격 메일 발송 여부를 확인해 전달한다.
     */
    @Transactional
    public void guideChanged(UUID companyId, UUID stageId, LocalDate date, boolean allowReassignment) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        int seq = stage.seq();
        StageInfo previous = recruitment.stages().stream().filter(item -> item.seq() == seq - 1)
                .findFirst().orElse(null);
        if (stage.type() != StageType.INTERVIEW || previous == null
                || (previous.status() != StageStatus.CONFIRMED && previous.status() != StageStatus.DONE)) {
            return;
        }
        recruits.lockStage(companyId, previous.id());
        recruits.lockStage(companyId, stageId);
        stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (Objects.equals(stage.guide().schedule(), date)
                || (stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE)) {
            return;
        }
        InterviewSchedulingJob job = jobs.findByPreviousStageIdAndCompanyId(previous.id(), companyId)
                .orElseGet(() -> new InterviewSchedulingJob(previous.id(), companyId, stageId));
        if ("READY".equals(job.getStatus()) && !allowReassignment) {
            return;
        }
        job.reassignAutomatic(allowReassignment);
        job.change(date == null ? "DATE_REQUIRED" : "PENDING", null);
        jobs.save(job);
        if (date != null) {
            events.publishEvent(new InterviewScheduleRequested(companyId, previous.id()));
        }
    }

    /** 결과 확정 트랜잭션 또는 HR 재시도 요청에서 대기 상태와 영속 비동기 이벤트만 기록한다. */
    @Transactional
    public Status request(UUID companyId, UUID previousStageId) {
        recruits.lockStage(companyId, previousStageId);
        RecruitmentInfo recruitment = recruits.getByStage(companyId, previousStageId);
        StageInfo previous = recruitment.stage(previousStageId).orElseThrow();
        if (previous.status() != StageStatus.CONFIRMED && previous.status() != StageStatus.DONE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_CONFIRMED", "Confirm the results first.");
        }
        StageInfo next = next(recruitment, previous);
        if (next == null || next.type() != StageType.INTERVIEW) {
            return new Status("NOT_APPLICABLE", null, null);
        }
        InterviewSchedulingJob job = jobs.findByPreviousStageIdAndCompanyId(previousStageId, companyId)
                .orElseGet(() -> new InterviewSchedulingJob(previousStageId, companyId, next.id()));
        if (!"READY".equals(job.getStatus())) {
            job.change(next.guide().schedule() == null ? "DATE_REQUIRED" : "PENDING", null);
            jobs.save(job);
            if ("PENDING".equals(job.getStatus())) {
                events.publishEvent(new InterviewScheduleRequested(companyId, previousStageId));
            }
        }
        return new Status(job.getStatus(), next.id(), job.getErrorCode());
    }

    @Transactional(readOnly = true)
    public Status status(UUID companyId, UUID previousStageId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, previousStageId);
        StageInfo next = next(recruitment, recruitment.stage(previousStageId).orElseThrow());
        if (next == null || next.type() != StageType.INTERVIEW) {
            return new Status("NOT_APPLICABLE", null, null);
        }
        return jobs.findByPreviousStageIdAndCompanyId(previousStageId, companyId)
                .map(job -> new Status(job.getStatus(), next.id(), job.getErrorCode()))
                .orElseGet(() -> new Status("NOT_REQUESTED", next.id(), null));
    }

    /** 배정 하나가 실패하면 이번에 만든 시간 전체를 롤백한다. 재시도해도 이미 있던 시간은 바꾸지 않는다. */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void execute(UUID companyId, UUID previousStageId) {
        recruits.lockStage(companyId, previousStageId);
        InterviewSchedulingJob job = jobs.findByPreviousStageIdAndCompanyId(previousStageId, companyId).orElseThrow();
        if (!"PENDING".equals(job.getStatus())) {
            return;
        }
        assignNext(companyId, previousStageId, job.isReassignAutomatic());
        job.change("READY", null);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failed(UUID companyId, UUID previousStageId, RuntimeException error) {
        recruits.lockStage(companyId, previousStageId);
        jobs.findByPreviousStageIdAndCompanyId(previousStageId, companyId).ifPresent(job -> {
            if ("PENDING".equals(job.getStatus())) {
                job.change("FAILED", error instanceof ApiException api ? api.code() : "INTERVIEW_SCHEDULE_FAILED");
            }
        });
    }

    private static StageInfo next(RecruitmentInfo recruitment, StageInfo previous) {
        return recruitment.stages().stream().filter(stage -> stage.seq() == previous.seq() + 1)
                .findFirst().orElse(null);
    }

    public record Status(String status, @Schema(nullable = true) UUID nextStageId,
            @Schema(nullable = true) String errorCode) {
    }

    /**
     * 안내 날짜가 있는 다음 면접만 접수번호 순으로 배정한다. 시간대는 한국 시간, 평일 하루 아홉 칸이다.
     * 칸이 충분하면 한 칸에 한 명씩, 모자라면 모든 칸에 고르게 나눠 같은 시간에 함께 면접을 보게 한다.
     * 한 칸의 인원에 상한은 없고, 배정할 칸이 하나도 없을 때만 실패한다.
     */
    private void assignNext(UUID companyId, UUID previousStageId, boolean reassign) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, previousStageId);
        StageInfo previous = recruitment.stage(previousStageId).orElseThrow();
        StageInfo next = recruitment.stages().stream().filter(stage -> stage.seq() == previous.seq() + 1)
                .findFirst().orElse(null);
        if (next == null || next.guide().schedule() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_DATE_REQUIRED",
                    "Choose the interview date in the next stage guide.");
        }
        recruits.lockStage(companyId, next.id());
        List<UUID> passed = screening.results(companyId, previousStageId).passed();
        Map<UUID, InterviewSchedule> existing = schedules.findByStageIdAndCompanyId(next.id(), companyId).stream()
                .collect(Collectors.toMap(InterviewSchedule::getApplicationId, Function.identity()));
        Map<UUID, InterviewSession> sessionByApplicant = sessions.findByStageIdAndCompanyId(next.id(), companyId)
                .stream().collect(Collectors.toMap(InterviewSession::getApplicationId, Function.identity()));
        LocalDate limit = recruitment.stages().stream().filter(stage -> stage.seq() > next.seq())
                .map(stage -> stage.guide().schedule()).filter(java.util.Objects::nonNull)
                .min(Comparator.naturalOrder()).orElse(null);
        List<ApplicantInfo> applicants = applications.applicants(companyId, passed).stream()
                .sorted(Comparator.comparingInt(ApplicantInfo::applicationNo)).toList();
        // 수동 일정(직접 비운 시간 포함), 구분값이 없는 기존 일정, 이미 시작한 면접은 보존한다.
        List<ApplicantInfo> waiting = new ArrayList<>();
        for (ApplicantInfo applicant : applicants) {
            InterviewSchedule schedule = existing.get(applicant.applicationId());
            InterviewSession session = sessionByApplicant.get(applicant.applicationId());
            if (!begun(session) && (schedule == null || (reassign && schedule.isAutomaticallyScheduled()))) {
                waiting.add(applicant);
            }
        }
        if (waiting.isEmpty()) {
            return;
        }
        if (next.status() != StageStatus.PENDING && next.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_CLOSED",
                    "The interview stage is already confirmed.");
        }
        Set<UUID> moving = waiting.stream().map(ApplicantInfo::applicationId).collect(Collectors.toSet());
        List<Instant> occupied = existing.values().stream()
                .filter(schedule -> !moving.contains(schedule.getApplicationId()))
                .map(InterviewSchedule::getScheduledAt).filter(Objects::nonNull).toList();
        List<Instant> slots = openSlots(next.guide().schedule(), limit, waiting.size(), occupied,
                startedSlots(companyId, next.id(), existing));
        // 칸마다 이미 있는 인원을 세어, 몇 명씩 더 넣을지 먼저 정한다
        int[] counts = new int[slots.size()];
        for (int slot = 0; slot < counts.length; slot++) {
            counts[slot] = Collections.frequency(occupied, slots.get(slot));
        }
        int[] added = spread(counts, waiting.size());
        // 앞 칸부터 정해진 인원만큼 접수번호 순으로 채운다
        int person = 0;
        for (int slot = 0; slot < added.length; slot++) {
            for (int count = 0; count < added[slot]; count++) {
                UUID applicationId = waiting.get(person).applicationId();
                person++;
                InterviewSchedule schedule = existing.get(applicationId);
                if (schedule == null) {
                    schedule = new InterviewSchedule(next.id(), applicationId, companyId);
                }
                Instant start = slots.get(slot);
                if (!Objects.equals(schedule.getScheduledAt(), start)) {
                    InterviewSession session = sessionByApplicant.get(applicationId);
                    if (session != null && session.getStatus() == InterviewSessionStatus.ABSENT) {
                        session.rejoin(InterviewSessionStatus.SCHEDULED, null);
                    }
                    attendance.clear(next.id(), applicationId);
                }
                schedule.assignAutomatically(start);
                schedules.save(schedule);
                events.publishEvent(new InterviewSessionChanged(companyId, next.id(), applicationId));
            }
        }
    }

    private static boolean begun(InterviewSession session) {
        return session != null && (session.getStartedAt() != null
                || session.getStatus() == InterviewSessionStatus.IN_PROGRESS
                || session.getStatus() == InterviewSessionStatus.ENDED);
    }

    /**
     * 칸마다 새로 넣을 인원을 정한다. 지원자를 한 명씩 "지금 인원이 가장 적은 칸 중 가장 이른 칸"에 넣는다.
     * 그래서 칸이 충분하면 빈 칸에 한 명씩 들어가고, 모자라면 인원이 고르게 나뉘며 남는 사람은 앞 칸에 더 들어간다.
     *
     * @param counts 칸마다 이미 있는 인원
     * @param waiting 새로 넣을 지원자 수
     * @return 칸마다 새로 넣을 인원
     */
    static int[] spread(int[] counts, int waiting) {
        int[] total = counts.clone();
        int[] added = new int[counts.length];
        for (int person = 0; person < waiting; person++) {
            int smallest = 0;
            for (int slot = 1; slot < total.length; slot++) {
                if (total[slot] < total[smallest]) {
                    smallest = slot;
                }
            }
            total[smallest]++;
            added[smallest]++;
        }
        return added;
    }

    /** 이미 시작했거나 끝난 면접의 시간. 뒤늦게 다른 지원자가 합류하면 안 되므로 배정 칸에서 뺀다 */
    private Set<Instant> startedSlots(UUID companyId, UUID stageId, Map<UUID, InterviewSchedule> existing) {
        Set<Instant> started = new HashSet<>();
        for (InterviewSession session : sessions.findByStageIdAndCompanyId(stageId, companyId)) {
            InterviewSchedule schedule = existing.get(session.getApplicationId());
            boolean begun = session.getStatus() == InterviewSessionStatus.IN_PROGRESS
                    || session.getStatus() == InterviewSessionStatus.ENDED;
            if (begun && schedule != null && schedule.getScheduledAt() != null) {
                started.add(schedule.getScheduledAt());
            }
        }
        return started;
    }

    /**
     * 배정할 수 있는 칸을 이른 순서로 모은다. 다음 면접 날짜가 있으면 그 전날까지의 칸을 모두 모으고,
     * 없으면 기간에 끝이 없으니 지원자 수만큼 빈 칸이 모일 때까지만 모은다. 그래서 다음 면접 날짜가 없으면 항상 한 칸에 한 명이다.
     */
    private static List<Instant> openSlots(LocalDate first, LocalDate limit, int waiting, List<Instant> occupied,
            Set<Instant> started) {
        if (first.isBefore(LocalDate.now(KOREA))) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_PAST",
                    "Choose an upcoming interview date before sending.");
        }
        List<Instant> slots = new ArrayList<>();
        int empty = 0;
        LocalDate date = first;
        while (limit != null ? date.isBefore(limit) : empty < waiting) {
            if (date.getDayOfWeek() != DayOfWeek.SATURDAY && date.getDayOfWeek() != DayOfWeek.SUNDAY) {
                for (int hour : HOURS) {
                    Instant start = date.atTime(hour, 0).atZone(KOREA).toInstant();
                    if (isOpen(start, occupied, started)) {
                        slots.add(start);
                        if (!occupied.contains(start)) {
                            empty++;
                        }
                    }
                }
            }
            date = date.plusDays(1);
        }
        if (slots.isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_CAPACITY",
                    "There are no interview slots before the following stage. Adjust the stage dates.");
        }
        return slots;
    }

    /**
     * 아직 지나지 않았고 시작한 면접이 없는 칸인가. 담당자가 직접 정한 다른 시간(예: 9시 30분)과 겹치는 칸도 뺀다.
     * 면접관이 두 면접에 동시에 들어갈 수 없어서다. 시각이 정확히 같으면 겹침이 아니라 같은 면접이므로 함께 넣을 수 있다.
     */
    private static boolean isOpen(Instant start, List<Instant> occupied, Set<Instant> started) {
        if (!start.isAfter(Instant.now()) || started.contains(start)) {
            return false;
        }
        Instant end = start.plus(1, ChronoUnit.HOURS);
        return occupied.stream().noneMatch(time -> !time.equals(start) && time.isBefore(end)
                && time.plus(1, ChronoUnit.HOURS).isAfter(start));
    }
}
