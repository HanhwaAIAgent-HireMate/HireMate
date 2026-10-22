package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.QuestionSource;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingService;
import com.hiremate.screening.ScreeningService;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 맞춤 면접 질문 생성. 면접 전형이 시작되면 미리 만들고, AI Chat이면 Root Agent를 거쳐 더 만든다. 질문은 지원자 카드에 들어간다. */
@Service
public class InterviewAiService {

    private final InterviewService interviews;
    private final CompanyService companies;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ScreeningService screening;
    private final CandidateAnalyst analyst;
    private final InterviewAgent agent;

    public InterviewAiService(InterviewService interviews, CompanyService companies, ApplicationService applications,
            PostingService postings, ScreeningService screening, CandidateAnalyst analyst, InterviewAgent agent) {
        this.interviews = interviews;
        this.companies = companies;
        this.applications = applications;
        this.postings = postings;
        this.screening = screening;
        this.analyst = analyst;
        this.agent = agent;
    }

    /** 면접 전형 지원자들의 현재 · 이전 면접 질문과 답변. Root Agent가 Chat에서 읽는다. */
    public Map<UUID, InterviewView> views(UUID companyId, UUID stageId, List<UUID> applicationIds) {
        Map<UUID, InterviewView> views = new LinkedHashMap<>();
        applicationIds.forEach(applicationId -> views.put(applicationId,
                interviews.view(companyId, stageId, applicationId)));
        return views;
    }

    /** 지금 카드에 있는 질문 수. */
    public int count(UUID companyId, UUID stageId, UUID applicationId) {
        return interviews.view(companyId, stageId, applicationId).questions().size();
    }

    /** AI Chat 요청: 질문을 바로 만들어 카드에 넣는다. focus는 Root Agent가 정리한 확인할 점이다. */
    public InterviewView generate(UUID companyId, UUID stageId, UUID applicationId, String focus) {
        Inputs in = inputs(companyId, stageId, applicationId);
        return interviews.addQuestions(companyId, stageId, applicationId,
                agent.questions(in.applicant(), in.posting(), in.analysis(), in.current(), in.company(), focus),
                QuestionSource.AI);
    }

    /**
     * 면접 전형이 시작될 때 질문을 미리 만든다 (FR-27). stub은 바로 카드에 넣고, remote는 AI 워커에 맡겨
     * {@link InterviewQuestionResults}가 결과를 넣는다.
     */
    public void prepare(UUID companyId, UUID stageId, UUID applicationId) {
        Inputs in = inputs(companyId, stageId, applicationId);
        agent.prepare(InterviewAgent.jobTarget(companyId, stageId, applicationId), in.applicant(), in.posting(),
                in.analysis(), in.current(), in.company())
                .ifPresent(questions -> addPrepared(companyId, stageId, applicationId, questions));
    }

    /** 미리 만든 질문을 카드에 넣는다. 카드에 이미 있는 문장은 건너뛴다. */
    public void addPrepared(UUID companyId, UUID stageId, UUID applicationId, List<String> questions) {
        interviews.addQuestions(companyId, stageId, applicationId, questions, QuestionSource.AI);
    }

    /** 질문 생성 재료: 지원서 · 공고 · 서류 분석 · 지금 카드(이전 면접 기록 포함) · 회사 인재상과 조직 문화. */
    private Inputs inputs(UUID companyId, UUID stageId, UUID applicationId) {
        InterviewView current = interviews.view(companyId, stageId, applicationId);
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
