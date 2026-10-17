package com.hiremate.ai.application;

import com.hiremate.company.CompanyService;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
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

    public PostingAiAnswer request(UUID companyId, UUID recruitmentId, String message) {
        PostingDraftContext context = postings.draftContext(companyId, recruitmentId);
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
