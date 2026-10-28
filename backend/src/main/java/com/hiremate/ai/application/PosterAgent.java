package com.hiremate.ai.application;

import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterProposal;

/** 공고 디자인 화면의 Root가 공고 Agent를 호출해 만든 추천/수정안. */
public interface PosterAgent {
    PosterProposal design(PosterContext context, String request);
}
