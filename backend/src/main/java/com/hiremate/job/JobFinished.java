package com.hiremate.job;

/**
 * AI 워커가 작업을 끝냈다. 작업을 넣은 모듈이 type으로 자기 작업인지 보고 결과를 기록한다.
 * job 모듈은 결과를 이 이벤트로만 알리고 업무 모듈을 부르지 않는다.
 */
public record JobFinished(JobResult result) {
}
