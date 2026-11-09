package com.hiremate.apply;

/** 지원자 사진과 예시 사진 여부. */
public record ApplicationPhoto(byte[] bytes, String contentType, boolean example) {
}
