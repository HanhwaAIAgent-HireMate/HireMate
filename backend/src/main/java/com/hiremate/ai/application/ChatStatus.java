package com.hiremate.ai.application;

/**
 * Chat 처리 단계 문구. SSE status 이벤트의 data다. 문구는 코드 상수다 (모델이 쓴 문장이 아니다).
 *
 * @param depth 단계의 깊이. 0은 Root의 단계, 1은 그 아래에서 부른 도구나 하위 Agent의 일, 2는 그 일의 결과다.
 *     깊이가 없는 단계(예전 ai 서버)는 Root 단계로 받는다
 */
public record ChatStatus(String text, Integer depth) {

    public ChatStatus {
        depth = depth == null ? 0 : depth;
    }
}
