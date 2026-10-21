package com.hiremate.job;

import com.hiremate.job.application.JobStreams;
import java.util.UUID;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;

/**
 * 분석 작업 대기열. 작업을 Redis 작업 스트림에 넣으면 AI 워커가 꺼내 처리하고, 결과는 {@link JobFinished}로 알린다.
 * 넣는 쪽은 결과를 기다리지 않는다.
 */
@Service
public class JobQueue {

    private final JobStreams streams;
    private final JsonMapper json;

    public JobQueue(JobStreams streams, JsonMapper json) {
        this.streams = streams;
        this.json = json;
    }

    /**
     * 작업을 넣고 ID를 돌려준다.
     *
     * @param type ai 서버 경로와 같은 '{agent}/{method}'
     * @param target 작업 대상 (예: 지원서 ID)
     * @param payload 그 경로의 요청 본문. Agent 메서드의 매개변수 이름을 키로 한 Map을 넘긴다
     */
    public UUID enqueue(String type, String target, Object payload) {
        Job job = new Job(UUID.randomUUID(), type, target, json.valueToTree(payload));
        streams.add(job);
        return job.jobId();
    }

    /** 결과를 아직 받지 못한 작업이 있는가. Redis가 비면 false라, 넣은 모듈이 남은 작업을 다시 넣을 수 있다. */
    public boolean isOpen(String type, String target) {
        return streams.isOpen(type, target);
    }
}
