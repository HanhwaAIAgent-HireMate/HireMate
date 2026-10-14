package com.hiremate.posting;

import java.util.UUID;

/** 공고 접수가 끝나 첫 전형이 시작됐다. 전형 화면이 이 이벤트로 지원자를 첫 전형 대상에 넣는다. */
public record PostingClosed(UUID recruitmentId, UUID companyId, UUID firstStageId) {
}
