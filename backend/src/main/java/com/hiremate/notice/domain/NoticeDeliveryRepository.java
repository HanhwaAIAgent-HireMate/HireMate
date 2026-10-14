package com.hiremate.notice.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NoticeDeliveryRepository extends JpaRepository<NoticeDelivery, UUID> {

    List<NoticeDelivery> findByNoticeId(UUID noticeId);
}
