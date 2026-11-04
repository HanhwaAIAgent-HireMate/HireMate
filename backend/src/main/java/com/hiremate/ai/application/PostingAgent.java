package com.hiremate.ai.application;

import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import com.hiremate.posting.PostingSuggestion;
import java.util.List;

/**
 * Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 게시는 하지 않는다.
 * 문서를 고치는 요청만 받고, 수정안은 HR이 적용 여부를 정한다.
 */
public interface PostingAgent {

    /**
     * HR의 요청대로 공고 수정안을 만든다.
     *
     * @param posting 저장된 지금 공고
     * @param writingStyle 기업의 공고 작성 스타일
     * @param request HR의 수정 요청
     * @param focus HR이 고른 줄. 고르면 그 줄만 고치고, 고르지 않았으면 null이다
     * @param progress 처리 중 단계를 화면에 알린다. 화면 연결이 끊기면 UncheckedIOException으로 멈춘다
     * @return Chat에 보여 줄 답과 수정안
     */
    Result revise(PostingDraftContext posting, String writingStyle, String request, PostingFocus focus,
            ChatProgress progress);

    /**
     * @param reply Chat에 보여 줄 답
     * @param suggestion 수정안. 되묻거나 처리할 수 없는 요청이면 null
     * @param ncsSources 수정안이 참고했고 원문이 받쳐 준다고 판정한 NCS 출처. 참고하지 않았으면 빈 목록이다
     */
    record Result(String reply, PostingSuggestion suggestion, List<NcsSource> ncsSources) {

        public Result {
            ncsSources = ncsSources == null ? List.of() : List.copyOf(ncsSources);
        }

        /** NCS를 참고하지 않은 답. */
        public Result(String reply, PostingSuggestion suggestion) {
            this(reply, suggestion, List.of());
        }
    }

    /**
     * 수정안이 참고한 NCS 출처 하나. 공고 줄 하나와 그 줄을 받쳐 준 NCS 원문 문장이다.
     * HR이 보고 판단하는 참고자료라 Chat 답에만 보이고 공고와 수정안에는 저장하지 않는다.
     *
     * @param field 그 줄이 있는 공고 칸(duties, qualifications, preferred)
     * @param number 그 칸의 몇 번째 줄인지(1부터)
     * @param line 공고 줄
     * @param dutyName NCS 직무 이름
     * @param unitCode 능력단위 코드(버전 포함)
     * @param unitName 능력단위 이름
     * @param taskName 능력단위요소(주요 업무) 이름
     * @param sentence 원문 문장(책임 및 역할)
     */
    record NcsSource(String field, int number, String line, String dutyName, String unitCode, String unitName,
            String taskName, String sentence) {
    }
}
