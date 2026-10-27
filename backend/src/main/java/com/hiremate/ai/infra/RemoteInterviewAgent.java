package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.InterviewAgent;
import com.hiremate.ai.application.InterviewQuestionsRequest;
import com.hiremate.ai.application.InterviewerMemo;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewView;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingContent;
import java.util.List;
import java.util.Optional;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 맞춤 면접 질문 생성. AI Chat 요청은 POST /agents/interview/questions로 바로 부르고, 앞 전형 결과를 확정할 때
 * 미리 만드는 질문은 같은 요청 본문을 작업으로 대기열에 넣는다. 모델이 느려도 결과 확정 요청이 기다리지 않는다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.INTERVIEW, mode = AiMode.REMOTE)
class RemoteInterviewAgent implements InterviewAgent {

    private static final ParameterizedTypeReference<List<InterviewQuestionDraft>> QUESTIONS =
            new ParameterizedTypeReference<>() {
            };

    private final AiServerClient client;
    private final JobQueue jobs;

    RemoteInterviewAgent(AiServerClient client, JobQueue jobs) {
        this.client = client;
        this.jobs = jobs;
    }

    @Override
    public List<InterviewQuestionDraft> questions(ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus,
            Integer questionCount) {
        InterviewQuestionsRequest body = new InterviewQuestionsRequest(applicant, posting, analysis, interview, company,
                focus, questionCount);
        return client.post(AiAgent.INTERVIEW, "questions", body, QUESTIONS);
    }

    @Override
    public List<InterviewQuestionDraft> memoQuestions(ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company, String focus,
            InterviewerMemo memo) {
        return client.post(AiAgent.INTERVIEW, "questions",
                new InterviewQuestionsRequest(applicant, posting, analysis, interview, company, focus, 1, memo),
                QUESTIONS);
    }

    @Override
    public Optional<List<InterviewQuestionDraft>> prepare(String target, ApplicantDetail applicant,
            PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company) {
        jobs.enqueue(QUESTIONS_JOB, target,
                new InterviewQuestionsRequest(applicant, posting, analysis, interview, company, null, null));
        return Optional.empty();
    }

}
