package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import java.util.List;

/**
 * Interview Agent (면접 질문 생성). 이전 전형에서 확인된 내용 가운데 면접에서 더 확인할 가치가 있는 부분을 질문으로 만든다.
 */
public interface InterviewAgent {

    /**
     * @param focus HR이 정한 범위 (예: "기술은 확인했으니 확인 안 된 부분 중심으로"). 없으면 null
     */
    List<String> questions(ApplicantDetail applicant, PostingContent posting, CandidateAnalysis analysis,
            InterviewView interview, String focus);
}
