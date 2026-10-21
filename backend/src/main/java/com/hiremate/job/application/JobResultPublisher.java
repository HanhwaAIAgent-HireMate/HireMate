package com.hiremate.job.application;

import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 결과 스트림에서 꺼낸 결과를 {@link JobFinished}로 알린다. 트랜잭션 안에서 발행해 이벤트가 DB에 남은 뒤에
 * 결과 스트림에서 지운다. 받는 모듈은 @ApplicationModuleListener로 따로 처리한다.
 */
@Component
public class JobResultPublisher {

    private final ApplicationEventPublisher events;

    JobResultPublisher(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void publish(JobResult result) {
        events.publishEvent(new JobFinished(result));
    }
}
