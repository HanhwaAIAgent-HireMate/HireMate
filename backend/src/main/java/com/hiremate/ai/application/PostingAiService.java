package com.hiremate.ai.application;

import com.hiremate.company.CompanyService;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.recruit.RecruitmentStatus;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 공고 편집 화면의 AI 수정 요청. Root Agent를 거치지 않고 Posting Agent를 바로 부른다. */
@Service
public class PostingAiService {

    private final PostingService postings;
    private final CompanyService companies;
    private final PostingAgent agent;
    private final AiSettings settings;

    public PostingAiService(PostingService postings, CompanyService companies, PostingAgent agent,
            AiSettings settings) {
        this.postings = postings;
        this.companies = companies;
        this.agent = agent;
        this.settings = settings;
    }

    /** 게시한 공고는 바꿀 수 없어 Posting Agent를 부르지 않고 바로 답한다. */
    static final String PUBLISHED_REPLY = "게시한 공고는 바꿀 수 없어요. 전형 일정 · 장소는 전형별 안내에서 고칠 수 있어요.";

    public PostingAiAnswer request(UUID companyId, UUID recruitmentId, String message) {
        PostingDraftContext context = postings.draftContext(companyId, recruitmentId);
        if (context.status() != RecruitmentStatus.DRAFT) {
            return new PostingAiAnswer(PUBLISHED_REPLY, "Posting Agent", settings.isStub(AiAgent.POSTING),
                    postings.view(companyId, recruitmentId));
        }
        PostingAgent.Result result = agent.revise(context,
                companies.postingSettings(companyId).writingStyle(), message);
        PostingView posting = result.suggestion() == null
                ? postings.view(companyId, recruitmentId)
                : postings.suggest(companyId, recruitmentId, result.suggestion());
        return new PostingAiAnswer(result.reply(), "Posting Agent", settings.isStub(AiAgent.POSTING), posting);
    }

    public record PostingAiAnswer(String reply, String agent, boolean stub, PostingView posting) {
    }
}
