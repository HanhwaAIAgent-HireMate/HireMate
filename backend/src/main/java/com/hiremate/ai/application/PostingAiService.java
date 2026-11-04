package com.hiremate.ai.application;

import com.hiremate.company.CompanyService;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.recruit.RecruitmentStatus;
import java.util.List;
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

    /** 고른 줄이 저장된 공고에 없으면(다른 창에서 지웠을 때 등) Posting Agent를 부르지 않고 다시 고르게 한다. */
    static final String FOCUS_MISSING_REPLY = "고른 줄을 공고에서 찾지 못했어요. 줄을 다시 골라 주세요.";

    /**
     * Posting Agent에게 수정안을 받아 공고에 수정안으로 남긴다. 적용은 HR이 한다.
     *
     * @param focus HR이 고른 줄. 고르지 않았으면 null이다
     * @param progress Posting Agent의 처리 중 단계를 화면에 알린다
     */
    public PostingAiAnswer request(UUID companyId, UUID recruitmentId, String message, PostingFocus focus,
            ChatProgress progress) {
        PostingDraftContext context = postings.draftContext(companyId, recruitmentId);
        if (context.status() != RecruitmentStatus.DRAFT) {
            return answer(PUBLISHED_REPLY, postings.view(companyId, recruitmentId), List.of());
        }
        if (focus != null && !focus.isIn(context.content())) {
            return answer(FOCUS_MISSING_REPLY, postings.view(companyId, recruitmentId), List.of());
        }
        PostingAgent.Result result = agent.revise(context,
                companies.postingSettings(companyId).writingStyle(), message, focus, progress);
        PostingView posting = result.suggestion() == null
                ? postings.view(companyId, recruitmentId)
                : postings.suggest(companyId, recruitmentId, result.suggestion());
        return answer(result.reply(), posting, result.ncsSources());
    }

    private PostingAiAnswer answer(String reply, PostingView posting, List<PostingAgent.NcsSource> ncsSources) {
        return new PostingAiAnswer(reply, "Posting Agent", settings.isStub(AiAgent.POSTING), posting, ncsSources);
    }

    /**
     * @param ncsSources 수정안이 참고한 NCS 출처. 화면은 답 아래에 출처로 보인다. 참고하지 않았으면 빈 목록이다
     */
    public record PostingAiAnswer(String reply, String agent, boolean stub, PostingView posting,
            List<PostingAgent.NcsSource> ncsSources) {
    }
}
