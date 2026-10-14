package com.hiremate.file.application;

/** 파일 내용을 보관하는 저장소. 로컬 개발은 디스크, 운영은 비공개 S3를 쓴다. */
public interface FileStorage {

    void save(String key, byte[] content);

    byte[] load(String key);
}
