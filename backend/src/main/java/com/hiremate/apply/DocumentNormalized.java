package com.hiremate.apply;

import java.util.UUID;

/** 정제 JSON이 저장되어 검색용 색인을 만들 수 있다. */
public record DocumentNormalized(UUID documentId) {
}
