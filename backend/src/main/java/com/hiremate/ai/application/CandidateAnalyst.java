package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.posting.PostingContent;

/** 특정 지원자의 제출 자료를 공고 조건과 맞춰 본다 (Application Agent). */
public interface CandidateAnalyst {

    CandidateAnalysis analyze(ApplicantDetail applicant, PostingContent posting);
}
