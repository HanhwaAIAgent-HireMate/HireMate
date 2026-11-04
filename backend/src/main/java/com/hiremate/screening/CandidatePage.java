package com.hiremate.screening;

import java.util.List;
import java.util.UUID;

/**
 * schoolSuspects는 블라인드 채용 서류 전형에서 서류에 출신 학교를 쓴 지원자다. 리스트 맨 아래에 모이고, HR이 확인해 해제하면
 * 원래 자리로 돌아간다. 아직 불러오지 않은 쪽의 지원자까지 모두 담는다.
 */
public record CandidatePage(long total, List<CandidateRow> items, List<UUID> schoolSuspects) {

    public CandidatePage(long total, List<CandidateRow> items) {
        this(total, items, List.of());
    }
}
