package com.hiremate.apply;

import java.util.Arrays;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 명시된 가상 채용에만 시연용 사진을 배정한다. */
@Component
public class DemoApplicantPhotos {

    private static final Set<String> WOMAN_NAMES = words(
            "서연 서윤 지우 서현 민서 하은 하윤 윤서 지유 지민 채원 수아 지아 지윤 은서 다은 예은 수빈 소율 예린 하린 "
            + "유나 소희 세영 은영 지수 시은 민지 예진 다인 채은 나연 가은 서아 아린 은지 혜원 수연 지혜 유리 소연 "
            + "나래 연주 다현 유진 하율 채윤 예서 서영 지은 미영 은비 다연 연서 소은 나은 예나 지현 수진 혜진 미진 보람 슬기");
    private static final Set<String> MAN_NAMES = words(
            "민준 서준 도윤 예준 시우 하준 주원 지호 지후 준우 준서 도현 건우 현우 우진 선우 유준 정우 승우 승현 "
            + "시윤 준혁 은우 지훈 민재 태윤 기현 승민 민혁 준호 태현 동욱 승호 민성 성민 재원 재현 동현 상현 "
            + "시후 재윤 현준 진우 태민 민우 정민 성훈 영호 대현 종현 재훈 형준 경민 세훈 준영 윤호 현수 영민 지성 태양 이준");
    private static final Set<String> WOMAN_ENDINGS = words("아 은 연 희 린 나 미 혜 경 숙 정 영 비 리 솔 별 슬 람 랑");
    private static final Set<String> MAN_ENDINGS = words("준 우 호 훈 혁 민 재 석 철 규 성 환 욱 태 진 수 식 용 남 범 웅 찬 빈");

    private final Set<UUID> recruitments;

    public DemoApplicantPhotos(@Value("${hiremate.demo.photo-recruitments:}") String ids) {
        recruitments = Arrays.stream(ids.split(","))
                .map(String::trim)
                .filter(id -> !id.isEmpty())
                .map(UUID::fromString)
                .collect(Collectors.toUnmodifiableSet());
    }

    public boolean enabled(UUID recruitmentId) {
        return recruitments.contains(recruitmentId);
    }

    static int index(UUID applicationId, String name) {
        int hash = applicationId.hashCode();
        String trimmed = name.trim();
        int group = Math.floorMod(hash, 2);
        if (trimmed.matches("[가-힣]{2,4}")) {
            boolean doubleSurname = trimmed.matches("^(남궁|황보|제갈|선우|독고|사공).*") && trimmed.length() == 4;
            String given = trimmed.substring(doubleSurname ? 2 : 1);
            String ending = given.substring(given.length() - 1);
            if (WOMAN_NAMES.contains(given)) {
                group = 1;
            } else if (MAN_NAMES.contains(given)) {
                group = 0;
            } else if (WOMAN_ENDINGS.contains(ending)) {
                group = 1;
            } else if (MAN_ENDINGS.contains(ending)) {
                group = 0;
            }
        }
        return Math.floorMod(hash / 2, 4) * 2 + group;
    }

    private static Set<String> words(String text) {
        return Set.copyOf(Arrays.asList(text.split(" ")));
    }
}
