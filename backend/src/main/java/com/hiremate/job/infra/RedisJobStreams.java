package com.hiremate.job.infra;

import com.hiremate.job.Job;
import com.hiremate.job.application.JobStreams;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * Redis 작업 스트림. 작업은 'job' 필드에 JSON(contract/Job.json)으로 넣는다. 결과를 받을 때까지 대상마다
 * 열린 작업 표(스트림 이름 + ':open' 해시)에 작업 ID를 남긴다.
 */
@Component
class RedisJobStreams implements JobStreams {

    static final String JOB_FIELD = "job";

    private final StringRedisTemplate redis;
    private final JsonMapper json;
    private final String stream;

    RedisJobStreams(StringRedisTemplate redis, JsonMapper json, @Value("${hiremate.jobs.stream}") String stream) {
        this.redis = redis;
        this.json = json;
        this.stream = stream;
    }

    @Override
    public void add(Job job) {
        redis.opsForStream().add(StreamRecords.string(Map.of(JOB_FIELD, json.writeValueAsString(job)))
                .withStreamKey(stream));
        redis.opsForHash().put(openJobs(stream), openKey(job.type(), job.target()), job.jobId().toString());
    }

    @Override
    public boolean isOpen(String type, String target) {
        return redis.opsForHash().hasKey(openJobs(stream), openKey(type, target));
    }

    static String openJobs(String stream) {
        return stream + ":open";
    }

    static String openKey(String type, String target) {
        return type + ":" + target;
    }
}
