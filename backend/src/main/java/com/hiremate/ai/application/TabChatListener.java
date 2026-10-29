package com.hiremate.ai.application;

import com.hiremate.screening.TabDeleted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 탭을 지우면 그 탭의 AI Chat 대화방을 지운다 (대화방은 탭마다 하나). */
@Component
class TabChatListener {

    private static final Logger log = LoggerFactory.getLogger(TabChatListener.class);

    private final RootAgent root;

    TabChatListener(RootAgent root) {
        this.root = root;
    }

    @ApplicationModuleListener
    void on(TabDeleted event) {
        try {
            root.forget(ChatService.threadId(event.companyId(), event.stageId(), event.tabId()));
        } catch (RuntimeException exception) {
            log.warn("Chat thread was not deleted for tab {}", event.tabId(), exception);
        }
    }
}
