package com.hiremate.job.infra;

import com.hiremate.job.JobResult;
import com.hiremate.job.application.JobResultPublisher;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * Redis 결과 스트림을 소비자 그룹으로 읽어 {@link JobResultPublisher}로 알린 뒤 지운다. 알리지 못한 결과는 확인하지 않은
 * 채 남겨 두었다가 다시 읽는다. 결과를 받으면 그 대상의 열린 작업 표시를 지운다.
 */
@Component
class RedisJobResultReader {

    static final String RESULT_FIELD = "result";

    private static final Logger log = LoggerFactory.getLogger(RedisJobResultReader.class);
    private static final int BATCH = 20;

    private final StringRedisTemplate redis;
    private final JsonMapper json;
    private final JobResultPublisher publisher;
    private final String resultStream;
    private final String openJobs;
    private final String group;
    private final String consumer;
    private volatile boolean groupReady;

    RedisJobResultReader(StringRedisTemplate redis, JsonMapper json, JobResultPublisher publisher,
            @Value("${hiremate.jobs.stream}") String stream,
            @Value("${hiremate.jobs.result-stream}") String resultStream,
            @Value("${hiremate.jobs.group}") String group, @Value("${hiremate.jobs.consumer}") String consumer) {
        this.redis = redis;
        this.json = json;
        this.publisher = publisher;
        this.resultStream = resultStream;
        this.openJobs = RedisJobStreams.openJobs(stream);
        this.group = group;
        this.consumer = consumer;
    }

    @Scheduled(fixedDelayString = "${hiremate.jobs.poll-interval}")
    void readNew() {
        read(ReadOffset.lastConsumed());
    }

    /** 이 서버가 읽고 기록하지 못한 결과를 다시 읽는다. */
    @Scheduled(fixedDelayString = "${hiremate.jobs.retry-interval}")
    void readPending() {
        read(ReadOffset.from("0"));
    }

    private void read(ReadOffset offset) {
        try {
            ensureGroup();
            List<MapRecord<String, Object, Object>> records = redis.opsForStream().read(
                    Consumer.from(group, consumer), StreamReadOptions.empty().count(BATCH),
                    StreamOffset.create(resultStream, offset));
            if (records != null) {
                records.forEach(this::handle);
            }
        } catch (RuntimeException exception) {
            // Redis를 비웠으면 그룹부터 다시 만든다
            groupReady = false;
            log.warn("Job results could not be read: {}", exception.getMessage());
        }
    }

    private void ensureGroup() {
        if (groupReady) {
            return;
        }
        try {
            redis.opsForStream().createGroup(resultStream, ReadOffset.from("0"), group);
        } catch (DataAccessException exception) {
            if (!String.valueOf(exception.getMostSpecificCause().getMessage()).contains("BUSYGROUP")) {
                throw exception;
            }
        }
        groupReady = true;
    }

    private void handle(MapRecord<String, Object, Object> record) {
        JobResult result;
        try {
            result = json.readValue(String.valueOf(record.getValue().get(RESULT_FIELD)), JobResult.class);
        } catch (RuntimeException exception) {
            log.error("Unreadable job result {} was dropped", record.getId(), exception);
            remove(record);
            return;
        }
        try {
            publisher.publish(result);
        } catch (RuntimeException exception) {
            log.warn("Job result {} was not recorded and will be read again", result.jobId(), exception);
            return;
        }
        remove(record);
        String field = RedisJobStreams.openKey(result.type(), result.target());
        if (result.jobId().toString().equals(redis.opsForHash().get(openJobs, field))) {
            redis.opsForHash().delete(openJobs, field);
        }
    }

    private void remove(MapRecord<String, Object, Object> record) {
        redis.opsForStream().acknowledge(group, record);
        redis.opsForStream().delete(record);
    }
}
