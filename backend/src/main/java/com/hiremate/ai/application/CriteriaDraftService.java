package com.hiremate.ai.application;

import com.hiremate.global.ApiException;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningCriteriaView;
import com.hiremate.posting.ScreeningRubric;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/**
 * 공고 작성 화면의 서류 평가 기준 AI 초안. Posting Agent가 쓴 초안을 저장하지 않고 화면에 돌려준다.
 * HR이 고쳐 저장해야 서류 평가 기준이 된다. 게시한 뒤에는 기준을 바꿀 수 없어 초안도 쓰지 않는다.
 */
@Service
public class CriteriaDraftService {

    private final PostingService postings;
    private final PostingCriteriaAgent agent;
    private final AiSettings settings;

    public CriteriaDraftService(PostingService postings, PostingCriteriaAgent agent, AiSettings settings) {
        this.postings = postings;
        this.agent = agent;
        this.settings = settings;
    }

    /** 공고 항목 하나의 유형과 판정 기준 초안. 항목 문장은 공고의 자격요건 · 우대사항과 같아야 한다. */
    public CriterionDraftAnswer draft(UUID companyId, UUID recruitmentId, ScreeningRubric.Category category,
            String text) {
        ScreeningCriteriaView.CriterionItem item = draftable(companyId, recruitmentId).items().stream()
                .filter(found -> found.criterion().category() == category && found.criterion().text().equals(text))
                .findFirst()
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, "CRITERION_NOT_IN_POSTING",
                        "The item must be a qualification or preferred item of the posting."));
        PostingCriteriaAgent.CriterionDraft draft = agent.draftCriterion(content(companyId, recruitmentId),
                category, text, item.criterion().ncsUnitCode());
        return new CriterionDraftAnswer(draft, settings.isStub(AiAgent.POSTING));
    }

    /** 목록마다 '중요'로 추천할 항목. */
    public ImportantAnswer important(UUID companyId, UUID recruitmentId) {
        draftable(companyId, recruitmentId);
        return new ImportantAnswer(agent.recommendImportant(content(companyId, recruitmentId)),
                settings.isStub(AiAgent.POSTING));
    }

    private ScreeningCriteriaView draftable(UUID companyId, UUID recruitmentId) {
        ScreeningCriteriaView criteria = postings.screeningCriteria(companyId, recruitmentId);
        if (criteria.locked()) {
            throw new ApiException(HttpStatus.CONFLICT, "RECRUITMENT_LOCKED",
                    "Screening criteria cannot change after publishing.");
        }
        return criteria;
    }

    private PostingContent content(UUID companyId, UUID recruitmentId) {
        return postings.draftContext(companyId, recruitmentId).content();
    }

    /**
     * 항목 하나의 초안.
     *
     * @param stub 연습용 AI가 쓴 초안인지
     */
    public record CriterionDraftAnswer(PostingCriteriaAgent.CriterionDraft draft, boolean stub) {
    }

    /**
     * 목록마다 '중요' 추천.
     *
     * @param stub 연습용 AI가 고른 추천인지
     */
    public record ImportantAnswer(PostingCriteriaAgent.ImportantAdvice advice, boolean stub) {
    }
}
