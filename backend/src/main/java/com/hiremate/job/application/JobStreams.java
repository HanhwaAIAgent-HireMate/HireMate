package com.hiremate.job.application;

import com.hiremate.job.Job;

/** 작업을 넣는 Redis 스트림. 결과를 받기 전까지는 대상(type, target)마다 열린 작업으로 남겨 둔다. */
public interface JobStreams {

    void add(Job job);

    boolean isOpen(String type, String target);
}
