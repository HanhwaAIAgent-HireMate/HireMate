package com.hiremate.ai.application;

import com.hiremate.notice.NoticeDraftContext;

/** Communication Agent. 기업 안내 메일 양식의 AI 작성 영역만 쓴다. 필수 문구는 바꾸지 않고 발송하지 않는다. */
public interface CommunicationAgent {

    /**
     * @param request HR의 수정 요청. 처음 초안을 쓸 때는 null
     */
    Draft write(NoticeDraftContext notice, String request);

    record Draft(String reply, String content) {
    }
}
