package com.hiremate.interview;

import com.hiremate.interview.domain.InterviewAttendanceRepository;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArraySet;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 면접의 실시간 알림(SSE). 면접관 화면은 지원자 한 명의 면접을, HR 화면은 전형 전체를 구독한다.
 * 바뀌면 "changed" 신호만 보내고 화면이 다시 불러온다 (자료와 권한 판단은 조회 API 한 곳에 둔다).
 *
 * <p>면접관 화면의 연결이 열려 있는 동안을 "접속 중"으로 본다. 연결마다 15초마다 살아 있음을 보내며 마지막 접속 시각을
 * 남기고, 연결이 끊기면 다른 화면에 알린다. backend가 한 대라 연결은 메모리에 둔다 (여러 대가 되면 Redis로 옮긴다).
 */
@Component
public class InterviewLive {

    /** 연결이 끊긴 뒤 이만큼 지나 다시 알린다. 접속 판단의 유예 시간(InterviewAttendances.ONLINE)보다 길다 */
    private static final Duration OFFLINE_NOTICE = Duration.ofSeconds(25);

    private final Map<SessionKey, Set<Subscriber>> rooms = new ConcurrentHashMap<>();
    private final Map<UUID, Set<SseEmitter>> stages = new ConcurrentHashMap<>();
    private final InterviewAttendanceRepository attendance;
    private final ApplicationEventPublisher events;
    private final TaskScheduler later;

    public InterviewLive(InterviewAttendanceRepository attendance, ApplicationEventPublisher events,
            TaskScheduler later) {
        this.attendance = attendance;
        this.events = events;
        this.later = later;
    }

    private record SessionKey(UUID stageId, UUID applicationId) {
    }

    private record Subscriber(UUID memberId, SseEmitter emitter) {
    }

    /** 면접관 화면의 구독. 권한은 부르는 쪽이 먼저 확인한다. */
    public SseEmitter subscribe(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        SessionKey key = new SessionKey(stageId, applicationId);
        SseEmitter emitter = new SseEmitter(0L);
        Subscriber subscriber = new Subscriber(memberId, emitter);
        rooms.compute(key, (ignored, found) -> {
            Set<Subscriber> subscribers = found == null ? new CopyOnWriteArraySet<>() : found;
            subscribers.add(subscriber);
            return subscribers;
        });
        InterviewSessionChanged changed = new InterviewSessionChanged(companyId, stageId, applicationId);
        Runnable gone = () -> {
            rooms.computeIfPresent(key, (ignored, subscribers) -> {
                if (subscribers.remove(subscriber)) {
                    // 끊긴 뒤 유예 시간이 지나면 접속 끊김으로 보이도록 다시 알린다
                    later.schedule(() -> events.publishEvent(changed), Instant.now().plus(OFFLINE_NOTICE));
                }
                return subscribers.isEmpty() ? null : subscribers;
            });
        };
        emitter.onCompletion(gone);
        emitter.onTimeout(gone);
        emitter.onError(error -> gone.run());
        send(emitter, "connected");
        // 다른 화면이 접속 중으로 바로 보도록 알린다
        events.publishEvent(changed);
        return emitter;
    }

    /** HR 화면의 구독: 전형의 모든 면접. */
    public SseEmitter subscribeStage(UUID stageId) {
        SseEmitter emitter = new SseEmitter(0L);
        stages.compute(stageId, (ignored, found) -> {
            Set<SseEmitter> emitters = found == null ? new CopyOnWriteArraySet<>() : found;
            emitters.add(emitter);
            return emitters;
        });
        Runnable gone = () -> stages.computeIfPresent(stageId, (ignored, emitters) -> {
            emitters.remove(emitter);
            return emitters.isEmpty() ? null : emitters;
        });
        emitter.onCompletion(gone);
        emitter.onTimeout(gone);
        emitter.onError(error -> gone.run());
        send(emitter, "connected");
        return emitter;
    }

    /** 이 면접관이 지금 이 면접 화면을 열어 두었나. */
    public boolean connected(UUID stageId, UUID applicationId, UUID memberId) {
        return rooms.getOrDefault(new SessionKey(stageId, applicationId), Set.of()).stream()
                .anyMatch(subscriber -> subscriber.memberId().equals(memberId));
    }

    /** 바뀐 내용이 저장된 뒤에 알린다. 저장이 취소되면 알리지 않는다. */
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT, fallbackExecution = true)
    public void on(InterviewSessionChanged changed) {
        String data = "{\"applicationId\":\"" + changed.applicationId() + "\"}";
        rooms.getOrDefault(new SessionKey(changed.stageId(), changed.applicationId()), Set.of())
                .forEach(subscriber -> send(subscriber.emitter(), "changed", data));
        stages.getOrDefault(changed.stageId(), Set.of()).forEach(emitter -> send(emitter, "changed", data));
    }

    /** 연결을 살려 두고(프록시가 끊지 않게) 면접관의 마지막 접속 시각을 남긴다. */
    @Scheduled(fixedRate = 15_000)
    @Transactional
    public void keepAlive() {
        Instant now = Instant.now();
        rooms.forEach((key, subscribers) -> subscribers.forEach(subscriber -> {
            attendance.touch(key.stageId(), key.applicationId(), subscriber.memberId(), now);
            send(subscriber.emitter(), "ping");
        }));
        stages.values().forEach(emitters -> emitters.forEach(emitter -> send(emitter, "ping")));
    }

    private static void send(SseEmitter emitter, String name) {
        send(emitter, name, "{}");
    }

    private static void send(SseEmitter emitter, String name, String data) {
        try {
            emitter.send(SseEmitter.event().name(name).data(data));
        } catch (IOException | IllegalStateException gone) {
            emitter.completeWithError(gone);
        }
    }
}
