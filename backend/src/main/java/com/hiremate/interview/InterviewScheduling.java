package com.hiremate.interview;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.interview.domain.InterviewSchedulingJob;
import com.hiremate.interview.domain.InterviewSchedulingJobRepository;
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
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** HR의 결과 확정 뒤 다음 면접 일정을 배정한다. 기존 일정과 재시도 시각은 유지한다. */
@Service
public class InterviewScheduling {

    private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
    private static final List<Integer> HOURS = List.of(9, 10, 14, 15, 16);

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationService applications;
    private final InterviewScheduleRepository schedules;
    private final ApplicationEventPublisher events;
    private final InterviewSchedulingJobRepository jobs;

    public InterviewScheduling(RecruitService recruits, ScreeningService screening, ApplicationService applications,
            InterviewScheduleRepository schedules, ApplicationEventPublisher events,
            InterviewSchedulingJobRepository jobs) {
        this.recruits = recruits;
        this.screening = screening;
        this.applications = applications;
        this.schedules = schedules;
        this.events = events;
        this.jobs = jobs;
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
        assignNext(companyId, previousStageId);
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

    /** 안내 날짜가 있는 다음 면접만 접수번호 순으로 배정한다. 시간대는 한국 시간, 평일 하루 다섯 칸이다. */
    private Map<UUID, Instant> assignNext(UUID companyId, UUID previousStageId) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, previousStageId);
        StageInfo previous = recruitment.stage(previousStageId).orElseThrow();
        StageInfo next = recruitment.stages().stream().filter(stage -> stage.seq() == previous.seq() + 1)
                .findFirst().orElse(null);
        if (next == null || next.guide().schedule() == null) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_DATE_REQUIRED",
                    "Choose the interview date in the posting stage guide.");
        }
        recruits.lockStage(companyId, next.id());
        List<UUID> passed = screening.results(companyId, previousStageId).passed();
        Map<UUID, InterviewSchedule> existing = schedules.findByStageIdAndCompanyId(next.id(), companyId).stream()
                .collect(Collectors.toMap(InterviewSchedule::getApplicationId, Function.identity()));
        List<Instant> occupied = new ArrayList<>(existing.values().stream()
                .map(InterviewSchedule::getScheduledAt).filter(java.util.Objects::nonNull).toList());
        LocalDate limit = recruitment.stages().stream().filter(stage -> stage.seq() > next.seq())
                .map(stage -> stage.guide().schedule()).filter(java.util.Objects::nonNull)
                .min(Comparator.naturalOrder()).orElse(null);
        List<ApplicantInfo> applicants = applications.applicants(companyId, passed).stream()
                .sorted(Comparator.comparingInt(ApplicantInfo::applicationNo)).toList();
        Map<UUID, Instant> result = new LinkedHashMap<>();
        LocalDate date = next.guide().schedule();
        for (ApplicantInfo applicant : applicants) {
            InterviewSchedule schedule = existing.get(applicant.applicationId());
            if (schedule == null || schedule.getScheduledAt() == null) {
                if (next.status() != StageStatus.PENDING && next.status() != StageStatus.ACTIVE) {
                    throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_CLOSED",
                            "The interview stage is already confirmed.");
                }
                Instant start = available(date, limit, occupied);
                if (schedule == null) {
                    schedule = new InterviewSchedule(next.id(), applicant.applicationId(), companyId);
                }
                schedule.change(start, schedule.getInterviewers());
                schedules.save(schedule);
                occupied.add(start);
                date = start.atZone(KOREA).toLocalDate();
                events.publishEvent(new InterviewSessionChanged(companyId, next.id(), applicant.applicationId()));
            }
            result.put(applicant.applicationId(), schedule.getScheduledAt());
        }
        return result;
    }

    private static Instant available(LocalDate first, LocalDate limit, List<Instant> occupied) {
        if (first.isBefore(LocalDate.now(KOREA))) {
            throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_PAST",
                    "Choose an upcoming interview date before sending.");
        }
        LocalDate date = first;
        while (limit == null || date.isBefore(limit)) {
            if (date.getDayOfWeek() != DayOfWeek.SATURDAY && date.getDayOfWeek() != DayOfWeek.SUNDAY) {
                for (int hour : HOURS) {
                    Instant start = date.atTime(hour, 0).atZone(KOREA).toInstant();
                    Instant end = start.plus(1, ChronoUnit.HOURS);
                    if (start.isAfter(Instant.now()) && occupied.stream()
                            .noneMatch(time -> time.isBefore(end) && time.plus(1, ChronoUnit.HOURS).isAfter(start))) {
                        return start;
                    }
                }
            }
            date = date.plusDays(1);
        }
        throw new ApiException(HttpStatus.CONFLICT, "INTERVIEW_SCHEDULE_CAPACITY",
                "There are no interview slots before the following stage. Adjust the stage dates.");
    }
}
