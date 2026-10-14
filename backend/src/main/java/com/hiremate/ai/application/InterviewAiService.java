package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewView;
import com.hiremate.interview.QuestionSource;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingService;
import com.hiremate.screening.ScreeningService;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 맞춤 면접 질문 생성. 화면 버튼이면 바로, AI Chat이면 Root Agent를 거쳐 부른다. 질문은 지원자 카드에 들어간다. */
@Service
public class InterviewAiService {

    private final InterviewService interviews;
    private final ApplicationService applications;
    private final PostingService postings;
    private final ScreeningService screening;
    private final CandidateAnalyst analyst;
    private final InterviewAgent agent;

    public InterviewAiService(InterviewService interviews, ApplicationService applications, PostingService postings,
            ScreeningService screening, CandidateAnalyst analyst, InterviewAgent agent) {
        this.interviews = interviews;
        this.applications = applications;
        this.postings = postings;
        this.screening = screening;
        this.analyst = analyst;
        this.agent = agent;
    }

    /** 지금 카드에 있는 질문 수. */
    public int count(UUID companyId, UUID stageId, UUID applicationId) {
        return interviews.view(companyId, stageId, applicationId).questions().size();
    }

    public InterviewView generate(UUID companyId, UUID stageId, UUID applicationId, String focus) {
        InterviewView current = interviews.view(companyId, stageId, applicationId);
        ApplicantDetail applicant = applications.detail(companyId, applicationId);
        PostingContent posting = postings.draftContext(companyId,
                screening.overview(companyId, stageId).recruitmentId()).content();
        return interviews.addQuestions(companyId, stageId, applicationId,
                agent.questions(applicant, posting, analyst.analyze(applicant, posting), current, focus),
                QuestionSource.AI);
    }
}
