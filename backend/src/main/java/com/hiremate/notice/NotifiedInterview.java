package com.hiremate.notice;

import java.time.Instant;
import java.util.UUID;

/**
 * 면접 전형 지원자 한 명에게 앞 전형의 합격 안내 메일로 안내한 면접 일시. 면접 화면이 지금 일정과 비교해, 발송 뒤 바뀐
 * 일정이면 지원자에게 별도 안내가 필요하다고 알린다.
 *
 * @param interviewAt 메일로 안내한 면접 일시
 * @param sentAt 그 메일을 보낸 때
 */
public record NotifiedInterview(UUID applicationId, Instant interviewAt, Instant sentAt) {
}
