package com.hiremate.interview;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.interview.domain.InterviewOpinion;
import com.hiremate.interview.domain.InterviewOpinionRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * HR 알림: 최근 7일 안에 시작한 면접, 끝난 면접, 면접관 의견이 모두 들어온 면접. 같은 시간에 함께 시작하거나 끝난 지원자는
 * 한 줄로 묶는다. HR이 결정할 때가 됐는지 알 수 있게 하고, 결정은 HR이 결정 바에서 한다.
 */
@Service
public class InterviewNotices {

    private static final Duration RECENT = Duration.ofDays(7);
    private static final int LIMIT = 20;

    private final InterviewSessionRepository sessions;
    private final InterviewOpinionRepository opinions;
    private final InterviewGroups groups;
    private final RecruitService recruits;
    private final ApplicationService applications;

    public InterviewNotices(InterviewSessionRepository sessions, InterviewOpinionRepository opinions,
            InterviewGroups groups, RecruitService recruits, ApplicationService applications) {
        this.sessions = sessions;
        this.opinions = opinions;
        this.groups = groups;
        this.recruits = recruits;
        this.applications = applications;
    }

    public enum Kind {
        /** 두 면접관이 모두 준비 완료해 시작했다 */
        STARTED,
        /** 두 면접관이 모두 [면접 종료]를 눌러 끝났다 */
        ENDED,
        /** 함께 끝난 지원자 모두에게 배정된 두 면접관의 의견이 들어왔다 */
        OPINIONS_DONE
    }

    /** 알림 한 줄. at은 그 일이 일어난 때다 (의견 완료는 마지막 의견을 처음 저장한 때). */
    public record InterviewNotice(Kind kind, UUID stageId, UUID recruitmentId, String recruitmentTitle,
            String stageName, @Schema(nullable = true) Instant scheduledAt, List<String> applicantNames, Instant at) {
    }

    /** 최근 것부터 20개. */
    @Transactional(readOnly = true)
    public List<InterviewNotice> recent(UUID companyId) {
        Instant since = Instant.now().minus(RECENT);
        PageRequest page = PageRequest.of(0, 200);
        List<InterviewNotice> notices = new ArrayList<>();
        together(sessions.startedSince(companyId, since, page), InterviewSession::getStartedAt)
                .forEach(members -> notices.add(notice(Kind.STARTED, members, members.getFirst().getStartedAt())));
        together(sessions.endedSince(companyId, since, page), InterviewSession::getEndedAt).forEach(members -> {
            notices.add(notice(Kind.ENDED, members, members.getFirst().getEndedAt()));
            opinionsDoneAt(members).ifPresent(at -> notices.add(notice(Kind.OPINIONS_DONE, members, at)));
        });
        return notices.stream().sorted(Comparator.comparing(InterviewNotice::at).reversed()).limit(LIMIT).toList();
    }

    /** 같은 전형에서 같은 때 함께 시작하거나 끝난 면접끼리 묶는다 (받은 순서를 지킨다). */
    private static List<List<InterviewSession>> together(List<InterviewSession> found,
            Function<InterviewSession, Instant> at) {
        Map<List<Object>, List<InterviewSession>> grouped = new LinkedHashMap<>();
        found.forEach(session -> grouped.computeIfAbsent(List.of(session.getStageId(), at.apply(session)),
                key -> new ArrayList<>()).add(session));
        return List.copyOf(grouped.values());
    }

    /** 함께 끝난 지원자 모두에게 배정된 두 면접관이 의견을 냈으면, 마지막 의견을 처음 저장한 때. */
    private Optional<Instant> opinionsDoneAt(List<InterviewSession> members) {
        Instant last = null;
        for (InterviewSession session : members) {
            Map<UUID, InterviewOpinion> byMember = opinions.findByStageIdAndApplicationIdAndCompanyId(
                    session.getStageId(), session.getApplicationId(), session.getCompanyId()).stream()
                    .collect(Collectors.toMap(InterviewOpinion::getMemberId, Function.identity()));
            for (UUID memberId : List.of(session.getHrMemberId(), session.getPracticalMemberId())) {
                InterviewOpinion opinion = byMember.get(memberId);
                if (opinion == null) {
                    return Optional.empty();
                }
                if (last == null || opinion.getCreatedAt().isAfter(last)) {
                    last = opinion.getCreatedAt();
                }
            }
        }
        return Optional.ofNullable(last);
    }

    private InterviewNotice notice(Kind kind, List<InterviewSession> members, Instant at) {
        InterviewSession first = members.getFirst();
        UUID companyId = first.getCompanyId();
        RecruitmentInfo recruit = recruits.getByStage(companyId, first.getStageId());
        List<UUID> ids = members.stream().map(InterviewSession::getApplicationId).toList();
        Map<UUID, String> names = applications.applicants(companyId, ids).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, ApplicantInfo::name));
        return new InterviewNotice(kind, first.getStageId(), recruit.id(), recruit.title(),
                recruit.stage(first.getStageId()).orElseThrow().name(),
                groups.scheduledAt(first.getStageId(), first.getApplicationId()),
                ids.stream().map(id -> names.getOrDefault(id, "")).toList(), at);
    }
}
