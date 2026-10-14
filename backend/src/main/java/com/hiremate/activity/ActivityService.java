package com.hiremate.activity;

import com.hiremate.activity.domain.ActivityLog;
import com.hiremate.activity.domain.ActivityLogRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 결정 · 확정 · 게시 · 발송처럼 채용에 영향을 주는 행동을 누가 언제 했는지 남긴다 (NFR-08). */
@Service
public class ActivityService {

    private final ActivityLogRepository logs;

    public ActivityService(ActivityLogRepository logs) {
        this.logs = logs;
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void record(UUID companyId, UUID actorId, String action, String targetType, UUID targetId, String detail) {
        logs.save(new ActivityLog(companyId, actorId, action, targetType, targetId, detail));
    }
}
