package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Interview Agent (면접 질문 생성). 이전 전형에서 확인된 내용 가운데 면접에서 더 확인할 가치가 있는 부분을 질문으로 만든다.
 *
 * <p>AI Chat 요청은 {@link #questions}로 바로 받는다. 앞 전형 결과를 확정할 때 미리 만드는 질문({@link #prepare})은 stub이면
 * 바로 돌려주고, remote면 작업을 대기열(job 모듈)에 넣고 빈 값을 돌려준다. AI 워커가 만든 질문은
 * {@link InterviewQuestionResults}가 카드에 넣는다 (FR-27).
 */
public interface InterviewAgent {

    /** 대기열 작업 유형. ai 서버 경로(/agents/interview/questions)와 같다. 작업 대상은 {@link #jobTarget}이다. */
    String QUESTIONS_JOB = "interview/questions";

    /**
     * @param company 회사 소개 설정의 조직 문화 · 인재상. 최종면접의 인성 · 조직 적응 질문 기준으로 쓴다
     * @param focus HR이 정한 범위 (예: "기술은 확인했으니 확인 안 된 부분 중심으로"). 없으면 null
     * @param questionCount Chat 추가 목표 개수. 최초 자동 생성은 null
     */
    List<InterviewQuestionDraft> questions(ApplicantDetail applicant, PostingContent posting,
            CandidateAnalysis analysis,
            InterviewView interview, CompanyProfile company, String focus,
            Integer questionCount);

    /** 앞 전형 결과를 확정할 때 질문을 미리 만든다. 매개변수는 {@link #questions}와 같고 범위(focus)는 없다. */
    Optional<List<InterviewQuestionDraft>> prepare(String target, ApplicantDetail applicant,
            PostingContent posting,
            CandidateAnalysis analysis, InterviewView interview, CompanyProfile company);

    /** 미리 만들기 작업의 대상. 질문을 넣을 카드를 '기업 ID:전형 ID:지원서 ID'로 적는다. */
    static String jobTarget(UUID companyId, UUID stageId, UUID applicationId) {
        return companyId + ":" + stageId + ":" + applicationId;
    }
}
