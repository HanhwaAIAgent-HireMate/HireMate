package com.hiremate.interview;

import java.util.List;
import java.util.UUID;

/** HR 지원자 목록의 의견 배지 한 줄: 지원자별 면접관 의견. */
public record CandidateOpinions(UUID applicationId, List<OpinionView> opinions) {
}
