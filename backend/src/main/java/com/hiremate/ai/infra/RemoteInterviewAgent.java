package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.InterviewAgent;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewView;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingContent;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 맞춤 면접 질문 생성. AI Chat 요청은 POST /agents/interview/questions로 바로 부르고, 면접 전형이 시작될 때
 * 미리 만드는 질문은 같은 요청 본문을 작업으로 대기열에 넣는다. 모델이 느려도 전형 종료 요청이 기다리지 않는다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.INTERVIEW, mode = AiMode.REMOTE)
class RemoteInterviewAgent implements InterviewAgent {

    private static final ParameterizedTypeReference<List<String>> QUESTIONS = new ParameterizedTypeReference<>() {
    };

    private final AiServerClient client;
    private final JobQueue jobs;

    RemoteInterviewAgent(AiServerClient client, JobQueue jobs) {
        this.client = client;
        this.jobs = jobs;
    }

    @Override
    public List<String> questions(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus) {
        Map<String, Object> body = body(applicant, posting, analysis, interview, company, focus);
        return client.post(AiAgent.INTERVIEW, "questions", body, QUESTIONS);
    }

    @Override
    public Optional<List<String>> prepare(String target, ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company) {
        jobs.enqueue(QUESTIONS_JOB, target, body(applicant, posting, analysis, interview, company, null));
        return Optional.empty();
    }

    /** 요청 본문. 키는 InterviewAgent.questions의 매개변수 이름이다. focus는 null일 수 있어 null을 받는 Map을 쓴다. */
    private static Map<String, Object> body(ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company, String focus) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("applicant", applicant);
        body.put("posting", posting);
        body.put("analysis", analysis);
        body.put("interview", interview);
        body.put("company", company);
        body.put("focus", focus);
        return body;
    }
}
