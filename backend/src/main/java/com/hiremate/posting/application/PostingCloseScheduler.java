package com.hiremate.posting.application;

import com.hiremate.posting.PostingService;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 접수 기간이 끝난 공고를 1분마다 마감하고 첫 전형을 시작한다. */
@Component
class PostingCloseScheduler {

    private final PostingService postings;

    PostingCloseScheduler(PostingService postings) {
        this.postings = postings;
    }

    @Scheduled(fixedDelayString = "${hiremate.posting.close-check-ms:60000}")
    void closeExpired() {
        postings.closeExpired(Instant.now());
    }
}
