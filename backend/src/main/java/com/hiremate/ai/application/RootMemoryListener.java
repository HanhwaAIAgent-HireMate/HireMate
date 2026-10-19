package com.hiremate.ai.application;

import com.hiremate.recruit.StageFinished;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 전형이 끝나면 그 전형의 AI Chat 대화방을 지운다 (대화 보관은 전형 종료까지). */
@Component
class RootMemoryListener {

    private static final Logger log = LoggerFactory.getLogger(RootMemoryListener.class);

    private final RootAgent root;

    RootMemoryListener(RootAgent root) {
        this.root = root;
    }

    @ApplicationModuleListener
    void on(StageFinished event) {
        try {
            root.forgetStage(event.stageId());
        } catch (RuntimeException exception) {
            log.warn("Chat threads were not deleted for stage {}", event.stageId(), exception);
        }
    }
}
