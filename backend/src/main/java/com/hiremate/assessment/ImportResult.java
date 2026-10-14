package com.hiremate.assessment;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/** 지원자 매칭 결과. 맞추지 못한 식별값은 HR이 직접 연결한다. */
public record ImportResult(int matched, int total, Map<String, UUID> matches, List<String> unmatched,
        boolean saved) {
}
