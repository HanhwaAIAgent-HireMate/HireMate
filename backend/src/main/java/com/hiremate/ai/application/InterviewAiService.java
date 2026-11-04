package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.KeptQuestions;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingService;
import com.hiremate.screening.ScreeningService;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/** 맞춤 면접 질문 생성. 앞 전형 결과를 확정하면 미리 만들고, AI Chat이면 Root Agent를 거쳐 더 만든다. 질문은 지원자 카드에 들어간다. */
@Service
public class InterviewAiService {

    private static final Logger log = LoggerFactory.getLogger(InterviewAiService.class);

    private final InterviewService interviews;
    private final CompanyService companies;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ScreeningService screening;
    private final CandidateAnalyst analyst;
    private final InterviewAgent agent;
    private final JobQueue jobs;
    private final AiSettings settings;

    public InterviewAiService(InterviewService interviews, CompanyService companies, ApplicationService applications,
            PostingService postings, ScreeningService screening, CandidateAnalyst analyst, InterviewAgent agent,
            JobQueue jobs, AiSettings settings) {
        this.interviews = interviews;
        this.companies = companies;
        this.applications = applications;
        this.postings = postings;
        this.screening = screening;
        this.analyst = analyst;
        this.agent = agent;
        this.jobs = jobs;
        this.settings = settings;
    }

    /** 면접 전형 지원자들의 현재 · 이전 면접 질문과 답변. Root Agent가 Chat에서 읽는다. */
    public Map<UUID, InterviewView> views(UUID companyId, UUID stageId, List<UUID> applicationIds) {
        Map<UUID, InterviewView> views = new LinkedHashMap<>();
        applicationIds.forEach(applicationId -> views.put(applicationId,
                interviews.view(companyId, stageId, applicationId)));
        return views;
    }

    /** 현재 카드와 이전 면접에 해당하는 메모만 Chat 조회에 제공한다. 자동 질문 생성에는 넣지 않는다. */
    public List<InterviewerMemo> memos(UUID companyId, UUID stageId, UUID applicationId) {
        InterviewView view = interviews.view(companyId, stageId, applicationId);
        return screening.history(companyId, applicationId).stream()
                .filter(item -> item.stageId().equals(stageId)
                        || view.previous().stream().anyMatch(previous -> previous.stageId().equals(item.stageId())))
                .filter(item -> !item.memo().isBlank())
                .map(item -> new InterviewerMemo(item.stageId(), item.stageName(), item.memo())).toList();
    }

    /** Root가 원문과 대조한 메모도 실행 전에 다시 검증한다. 삭제·수정된 메모는 사용하지 않는다. */
    public InterviewView generateFromMemo(UUID companyId, UUID stageId, UUID applicationId,
            String focus, InterviewerMemo memo) {
        return generateFromMemo(companyId, stageId, applicationId, focus, memo, null);
    }

    /** role이 있으면(면접관 모드 Chat) 만든 질문을 그 담당으로 넣는다. */
    public InterviewView generateFromMemo(UUID companyId, UUID stageId, UUID applicationId,
            String focus, InterviewerMemo memo, InterviewerRole role) {
        if (memo == null || memo.text() == null || memo.text().isBlank()
                || memos(companyId, stageId, applicationId).stream().noneMatch(actual ->
                        actual.stageId().equals(memo.stageId()) && actual.stageName().equals(memo.stageName())
                        && actual.text().contains(memo.text()))) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_MEMO", "면접 메모를 다시 조회해 주세요.");
        }
        Inputs in = inputs(companyId, stageId, applicationId, interviews.view(companyId, stageId, applicationId));
        return interviews.addGeneratedQuestions(companyId, stageId, applicationId,
                withRole(agent.memoQuestions(in.applicant(), in.posting(), in.analysis(), in.current(), in.company(),
                        focus, memo).stream()
                        .filter(question -> !question.text().equals(InterviewService.INTRO)).limit(1).toList(), role));
    }

    /** 지금 카드에 있는 질문의 id. */
    public Set<UUID> questionIds(UUID companyId, UUID stageId, UUID applicationId) {
        return interviews.view(companyId, stageId, applicationId).questions().stream()
                .map(InterviewView.Question::questionId).collect(Collectors.toSet());
    }

    /** Chat의 질문 교체. 답변 없는 AI 질문만 지운다. */
    public KeptQuestions clearAiQuestions(UUID companyId, UUID stageId, UUID applicationId) {
        return interviews.clearAiQuestions(companyId, stageId, applicationId);
    }

    /** HR의 명시적인 재생성 요청. 추가 요청과 달리 최초 면접 구성을 다시 만든다. */
    public void regenerate(UUID companyId, UUID stageId, UUID applicationId) {
        InterviewView current = interviews.view(companyId, stageId, applicationId);
        String target = InterviewAgent.jobTarget(companyId, stageId, applicationId);
        if (interviews.preparing(companyId, stageId, applicationId)
                || !settings.isStub(AiAgent.INTERVIEW) && jobs.isOpen(InterviewAgent.QUESTIONS_JOB, target)) {
            throw new ApiException(HttpStatus.CONFLICT, "QUESTIONS_PREPARING",
                    "Questions are already being generated.");
        }
        Inputs in = inputs(companyId, stageId, applicationId,
                new InterviewView(applicationId, current.schedule(), List.of(), current.previous(),
                        current.singleInterview()));
        interviews.clearQuestions(companyId, stageId, applicationId);
        agent.prepare(target, in.applicant(), in.posting(), in.analysis(), in.current(), in.company())
                .ifPresent(questions -> addPreparedDrafts(companyId, stageId, applicationId, questions));
    }

    /** AI Chat 요청: 질문을 바로 만들어 카드에 넣는다. focus는 Root Agent가 정리한 확인할 점이다. */
    public InterviewView generate(UUID companyId, UUID stageId, UUID applicationId, String focus) {
        return generate(companyId, stageId, applicationId, focus, 2);
    }

    /** Chat에서 요청한 문항 수까지만 추가한다. 기존 질문과 답변은 그대로 둔다. */
    public InterviewView generate(UUID companyId, UUID stageId, UUID applicationId, String focus, int limit) {
        return generate(companyId, stageId, applicationId, focus, limit, null);
    }

    /** role이 있으면(면접관 모드 Chat) 만든 질문을 그 담당으로 넣는다. */
    public InterviewView generate(UUID companyId, UUID stageId, UUID applicationId, String focus, int limit,
            InterviewerRole role) {
        Inputs in = inputs(companyId, stageId, applicationId, interviews.view(companyId, stageId, applicationId));
        return interviews.addGeneratedQuestions(companyId, stageId, applicationId,
                withRole(agent.questions(in.applicant(), in.posting(), in.analysis(), in.current(), in.company(),
                        focus, limit).stream().filter(question -> !question.text().equals(InterviewService.INTRO))
                        .limit(limit).toList(), role));
    }

    /** NCS 참고 Chat 요청의 결과. cited는 카드에 넣은 질문 가운데 NCS 원문을 인용한 질문이 있었는가다. */
    public record NcsGenerated(InterviewView view, boolean cited) {
    }

    /**
     * Root 계획이 NCS 참고를 정한 Chat 요청. {@link #generate(UUID, UUID, UUID, String, int, InterviewerRole)}와 같은 순서로
     * 질문을 넣고, 넣은 질문이 NCS를 인용했는지 함께 돌려준다.
     */
    public NcsGenerated generateWithNcs(UUID companyId, UUID stageId, UUID applicationId, String focus, int limit,
            InterviewerRole role, NcsUse ncs) {
        Inputs in = inputs(companyId, stageId, applicationId, interviews.view(companyId, stageId, applicationId));
        List<CitedQuestionDraft> added = agent.citedQuestions(in.applicant(), in.posting(), in.analysis(),
                in.current(), in.company(), focus, limit, ncs).stream()
                .filter(question -> !question.text().equals(InterviewService.INTRO)).limit(limit).toList();
        InterviewView view = interviews.addGeneratedQuestions(companyId, stageId, applicationId,
                withRole(added.stream().map(CitedQuestionDraft::draft).toList(), role));
        return new NcsGenerated(view, added.stream().anyMatch(CitedQuestionDraft::ncsCited));
    }

    private static List<InterviewQuestionDraft> withRole(List<InterviewQuestionDraft> drafts, InterviewerRole role) {
        return role == null ? drafts : drafts.stream()
                .map(draft -> new InterviewQuestionDraft(draft.text(), draft.reason(), role)).toList();
    }

    /**
     * 앞 전형 결과를 확정하면 질문을 미리 만든다 (FR-27). stub은 바로 카드에 넣고, remote는 AI 워커에 맡겨
     * {@link InterviewQuestionResults}가 결과를 넣는다.
     */
    public void prepare(UUID companyId, UUID stageId, UUID applicationId) {
        InterviewView current = interviews.preparationView(companyId, stageId, applicationId);
        String target = InterviewAgent.jobTarget(companyId, stageId, applicationId);
        if (!current.questions().isEmpty()) {
            interviews.finishPreparing(companyId, stageId, applicationId);
            return;
        }
        if (!settings.isStub(AiAgent.INTERVIEW) && jobs.isOpen(InterviewAgent.QUESTIONS_JOB, target)) {
            return;
        }
        Inputs in = inputs(companyId, stageId, applicationId, current);
        agent.prepare(InterviewAgent.jobTarget(companyId, stageId, applicationId), in.applicant(), in.posting(),
                in.analysis(), in.current(), in.company())
                .ifPresent(questions -> addPreparedDrafts(companyId, stageId, applicationId, questions));
    }

    /**
     * 이 지원자의 질문을 AI 워커가 아직 만드는 중인가. 카드가 '질문 생성 중'을 보여 주고 끝나면 다시 불러오는 데 쓴다.
     * stub은 바로 만들어 늘 false다. 대기열(Redis)을 읽지 못하면 만드는 중이 아니라고 본다.
     */
    public boolean preparing(UUID companyId, UUID stageId, UUID applicationId) {
        interviews.view(companyId, stageId, applicationId);  // 이 기업 · 전형의 지원자인지 확인한다 (아니면 예외)
        if (settings.isStub(AiAgent.INTERVIEW)) {
            return false;
        }
        try {
            return interviews.preparing(companyId, stageId, applicationId) || jobs.isOpen(InterviewAgent.QUESTIONS_JOB,
                    InterviewAgent.jobTarget(companyId, stageId, applicationId));
        } catch (RuntimeException exception) {
            log.warn("Interview question job state could not be read for {}", applicationId, exception);
            return false;
        }
    }

    /** 생성 실패도 로딩을 끝내 담당자가 재생성을 요청할 수 있게 한다. */
    public void finishPreparing(UUID companyId, UUID stageId, UUID applicationId) {
        interviews.finishPreparing(companyId, stageId, applicationId);
    }

    /** 미리 만든 질문을 카드에 넣는다. 카드에 이미 있는 문장은 건너뛴다. */
    public void addPrepared(UUID companyId, UUID stageId, UUID applicationId, List<String> questions) {
        interviews.addPreparedQuestions(companyId, stageId, applicationId, questions);
    }

    /** 생성 시 선택한 근거를 문장과 함께 저장한다. */
    public void addPreparedDrafts(UUID companyId, UUID stageId, UUID applicationId,
            List<InterviewQuestionDraft> questions) {
        interviews.addPreparedDrafts(companyId, stageId, applicationId, questions);
        interviews.finishPreparing(companyId, stageId, applicationId);
    }

    /**
     * 🎤 [꼬리질문 받기]: 처음 질문부터 지금 질문까지의 질문과 답을 보고 꼬리질문 2개를 제안받는다. 저장하지 않는다.
     * 면접관이 하나를 고르면 {@link InterviewService#addFollowUp}으로 넣는다.
     *
     * <p>진행 중인 면접인지, 답을 적었는지, 2단계를 넘지 않는지는 모델을 부르기 전에 확인한다 (토큰을 쓰지 않는다).
     * 제안 문장에 차별 조건이 섞였는지는 ai 서버가 걸러 낸다.
     *
     * @param avoid [다시 제안]이면 앞서 보여 준 제안
     */
    public InterviewFollowUps followUps(UUID companyId, UUID stageId, UUID questionId, List<String> avoid) {
        List<InterviewView.Question> chain = interviews.followUpChain(companyId, stageId, questionId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        PostingContent posting = postings.draftContext(companyId, recruitmentId).content();
        InterviewFollowUps found = agent.followUps(new InterviewFollowUpsRequest(posting, chain, avoid));
        List<InterviewFollowUps.Suggestion> suggestions = found.suggestions().stream()
                .filter(suggestion -> suggestion.text() != null && !suggestion.text().isBlank())
                .limit(2).toList();
        return found.needed() && !suggestions.isEmpty() ? new InterviewFollowUps(true, suggestions)
                : InterviewFollowUps.none();
    }

    /** 질문 생성 재료: 지원서 · 공고 · 서류 분석 · 지금 카드(이전 면접 기록 포함) · 회사 인재상과 조직 문화. */
    private Inputs inputs(UUID companyId, UUID stageId, UUID applicationId, InterviewView current) {
        ApplicantDetail applicant = applications.detail(companyId, applicationId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        PostingContent posting = postings.draftContext(companyId, recruitmentId).content();
        CandidateAnalysis analysis = analyst.analyze(applicant, posting,
                postings.screeningRubric(companyId, recruitmentId));
        return new Inputs(applicant, posting, analysis, current, companies.profile(companyId));
    }

    private record Inputs(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView current, CompanyProfile company) {
    }
}
