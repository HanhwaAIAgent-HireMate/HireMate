package com.hiremate.interview;

import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import java.time.Instant;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * 면접 시간 묶음. 같은 전형에서 면접 일시가 같은 지원자는 한 면접(1:1이든 다대다든)으로 함께 준비 완료하고,
 * 함께 시작하고, 함께 끝낸다. 일정이 없는 지원자는 어느 묶음에도 들지 않아 면접을 시작할 수 없다.
 * 지원자마다의 질문 · 답변 · 메모 · 의견은 지금처럼 지원자 한 명의 면접(InterviewSession)에 남는다.
 */
@Component
class InterviewGroups {

    private final InterviewSessionRepository sessions;
    private final InterviewScheduleRepository schedules;

    InterviewGroups(InterviewSessionRepository sessions, InterviewScheduleRepository schedules) {
        this.sessions = sessions;
        this.schedules = schedules;
    }

    /** 이 지원자의 면접 일시. 정하지 않았으면 null */
    Instant scheduledAt(UUID stageId, UUID applicationId) {
        return schedules.findById(new InterviewSchedule.Key(stageId, applicationId))
                .map(InterviewSchedule::getScheduledAt).orElse(null);
    }

    /** 전형의 지원자별 면접 일시. 정하지 않은 지원자는 없다 */
    Map<UUID, Instant> stageSchedule(UUID companyId, UUID stageId) {
        Map<UUID, Instant> found = new HashMap<>();
        schedules.findByStageIdAndCompanyId(stageId, companyId).stream()
                .filter(schedule -> schedule.getScheduledAt() != null)
                .forEach(schedule -> found.put(schedule.getApplicationId(), schedule.getScheduledAt()));
        return found;
    }

    /** 이 면접과 같은 시간 면접 (불참 포함, 지원서 ID 문자열 순). 일정이 없으면 이 면접 하나다 */
    List<InterviewSession> members(InterviewSession session) {
        return byApplication(sessions.findByStageIdAndCompanyId(session.getStageId(), session.getCompanyId()),
                stageSchedule(session.getCompanyId(), session.getStageId())).get(session.getApplicationId());
    }

    /** 전형의 면접마다 같은 시간 면접 (불참 포함). 일정이 없는 면접은 자기 하나다 */
    static Map<UUID, List<InterviewSession>> byApplication(List<InterviewSession> all, Map<UUID, Instant> at) {
        Map<Instant, List<InterviewSession>> slots = all.stream()
                .filter(session -> at.containsKey(session.getApplicationId()))
                .sorted(Comparator.comparing(session -> session.getApplicationId().toString()))
                .collect(Collectors.groupingBy(session -> at.get(session.getApplicationId())));
        Map<UUID, List<InterviewSession>> groups = new HashMap<>();
        for (InterviewSession session : all) {
            Instant slot = at.get(session.getApplicationId());
            groups.put(session.getApplicationId(), slot == null ? List.of(session) : slots.get(slot));
        }
        return groups;
    }

    /** 불참을 뺀 지원자들 */
    static List<InterviewSession> present(List<InterviewSession> members) {
        return members.stream().filter(session -> session.getStatus() != InterviewSessionStatus.ABSENT).toList();
    }

    /** 같은 시간 면접의 상태. 한 명이라도 진행 중이면 진행 중, 불참을 뺀 모두가 끝났으면 종료, 그 밖에는 예정이다 */
    static InterviewSessionStatus status(List<InterviewSession> members) {
        List<InterviewSession> present = present(members);
        if (present.stream().anyMatch(session -> session.getStatus() == InterviewSessionStatus.IN_PROGRESS)) {
            return InterviewSessionStatus.IN_PROGRESS;
        }
        if (!present.isEmpty() && present.stream()
                .allMatch(session -> session.getStatus() == InterviewSessionStatus.ENDED)) {
            return InterviewSessionStatus.ENDED;
        }
        return present.isEmpty() ? InterviewSessionStatus.ABSENT : InterviewSessionStatus.SCHEDULED;
    }

    /** 같은 시간 면접의 시작 시각 (진행 중이거나 끝난 지원자 중 하나) */
    static Instant startedAt(List<InterviewSession> members) {
        return members.stream().map(InterviewSession::getStartedAt).filter(Objects::nonNull).findFirst().orElse(null);
    }
}
