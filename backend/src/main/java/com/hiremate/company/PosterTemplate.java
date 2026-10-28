package com.hiremate.company;

import java.util.UUID;

/** 기본 레이아웃과 회사 배색으로 저장한 이름 있는 기업 전용 템플릿. */
public record PosterTemplate(UUID id, String name, String template, String mood, String color, int decoration) {
}
