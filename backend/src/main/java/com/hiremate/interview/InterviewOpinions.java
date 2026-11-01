package com.hiremate.interview;

import com.hiremate.activity.ActivityService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewOpinion;
import com.hiremate.interview.domain.InterviewOpinionRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageStatus;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접관 의견: 배정된 면접관이 지원자마다 남기는 추천도와 이유. HR은 이 의견과 기록을 보고 직접 결정한다.
 *
 * <p>면접관끼리는 내 의견을 저장한 뒤에야 상대의 의견 내용을 본다 (먼저 본 의견에 판단이 끌려가지 않게). HR은 언제나
 * 모든 의견을 본다. 의견은 AI(Root Chat, 리포트, 답변 분석)에 넘기지 않는다.
 */
@Service
public class InterviewOpinions {

    private final InterviewOpinionRepository opinions;
    private final InterviewSessionRepository sessions;
    private final RecruitService recruits;
    private final ActivityService activity;

    public InterviewOpinions(InterviewOpinionRepository opinions, InterviewSessionRepository sessions,
            RecruitService recruits, ActivityService activity) {
        this.opinions = opinions;
        this.sessions = sessions;
        this.recruits = recruits;
        this.activity = activity;
    }

    /** 면접관이 보는 의견. 배정된 계정만 연다. */
    @Transactional(readOnly = true)
    public List<OpinionView> forInterviewer(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = assigned(companyId, stageId, applicationId, memberId);
        List<InterviewOpinion> found = opinions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId,
                companyId);
        boolean own = found.stream().anyMatch(opinion -> opinion.getMemberId().equals(memberId));
        return views(session, found, memberId, own);
    }

    /** 내 의견을 쓰거나 고친다. 진행 중인 전형에서만 된다. */
    @Transactional
    public List<OpinionView> save(UUID companyId, UUID stageId, UUID applicationId, UUID memberId,
            String memberName, Recommendation recommendation, String comment) {
        InterviewSession session = assigned(companyId, stageId, applicationId, memberId);
        StageStatus status = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status();
        if (status != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "Opinions are written during the stage.");
        }
        InterviewOpinion opinion = opinions.findById(new InterviewOpinion.Key(stageId, applicationId, memberId))
                .orElseGet(() -> new InterviewOpinion(stageId, applicationId, memberId, companyId));
        opinion.write(memberName, session.roleOf(memberId), recommendation, comment.strip());
        opinions.save(opinion);
        activity.record(companyId, memberId, "SAVE_INTERVIEW_OPINION", "APPLICATION", applicationId,
                stageId + ":" + recommendation);
        return forInterviewer(companyId, stageId, applicationId, memberId);
    }

    /** HR이 보는 지원자 한 명의 의견. 모두 보인다. */
    @Transactional(readOnly = true)
    public List<OpinionView> forHr(UUID companyId, UUID stageId, UUID applicationId) {
        recruits.getByStage(companyId, stageId);
        return sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .map(session -> views(session, opinions.findByStageIdAndApplicationIdAndCompanyId(stageId,
                        applicationId, companyId), null, true))
                .orElse(List.of());
    }

    /** HR 지원자 목록의 의견 배지: 배정된 지원자마다 의견. */
    @Transactional(readOnly = true)
    public List<CandidateOpinions> stage(UUID companyId, UUID stageId) {
        recruits.getByStage(companyId, stageId);
        Map<UUID, List<InterviewOpinion>> byApplication = opinions.findByStageIdAndCompanyId(stageId, companyId)
                .stream().collect(Collectors.groupingBy(InterviewOpinion::getApplicationId));
        return sessions.findByStageIdAndCompanyId(stageId, companyId).stream()
                .map(session -> new CandidateOpinions(session.getApplicationId(), views(session,
                        byApplication.getOrDefault(session.getApplicationId(), List.of()), null, true)))
                .toList();
    }

    /** 배정된 담당(인사 · 실무) 순서의 의견 칸, 뒤에 배정이 바뀐 면접관의 의견. */
    private static List<OpinionView> views(InterviewSession session, List<InterviewOpinion> found, UUID viewer,
            boolean reveal) {
        Map<UUID, InterviewOpinion> byMember = found.stream()
                .collect(Collectors.toMap(InterviewOpinion::getMemberId, Function.identity()));
        List<OpinionView> views = new ArrayList<>();
        views.add(view(session.getHrMemberId(), InterviewerRole.HR, byMember.remove(session.getHrMemberId()),
                viewer, reveal, false));
        views.add(view(session.getPracticalMemberId(), InterviewerRole.PRACTICAL,
                byMember.remove(session.getPracticalMemberId()), viewer, reveal, false));
        byMember.values().forEach(opinion -> views.add(view(opinion.getMemberId(), opinion.getInterviewerRole(),
                opinion, viewer, reveal, true)));
        return views;
    }

    private static OpinionView view(UUID memberId, InterviewerRole role, InterviewOpinion opinion, UUID viewer,
            boolean reveal, boolean unassigned) {
        boolean mine = memberId.equals(viewer);
        if (opinion == null) {
            return new OpinionView(memberId, "", role, false, null, null, null, false, mine, unassigned);
        }
        boolean open = reveal || mine;
        return new OpinionView(memberId, opinion.getMemberName(), opinion.getInterviewerRole(), true,
                open ? opinion.getRecommendation() : null, open ? opinion.getComment() : null,
                open ? opinion.getUpdatedAt() : null, opinion.edited(), mine, unassigned);
    }

    private InterviewSession assigned(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId,
                companyId).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_SESSION_NOT_FOUND",
                        "Interview session not found."));
        if (session.roleOf(memberId) == null) {
            throw new ApiException(HttpStatus.FORBIDDEN, "INTERVIEW_ACCESS_DENIED",
                    "Only assigned interviewers can open opinions.");
        }
        return session;
    }
}
