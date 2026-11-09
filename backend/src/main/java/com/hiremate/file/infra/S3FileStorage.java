package com.hiremate.file.infra;

import com.hiremate.file.application.FileStorage;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

/** 비공개 S3 버킷에 저장하고 짧은 서명 URL로 파일을 읽는다. */
@Component
@ConditionalOnProperty(prefix = "hiremate.files", name = "storage", havingValue = "s3")
class S3FileStorage implements FileStorage {

    private final String bucket;
    private final S3Client client;
    private final S3Presigner presigner;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    @Autowired
    S3FileStorage(@Value("${hiremate.files.bucket}") String bucket) {
        this(bucket, S3Client.create(), S3Presigner.create());
    }

    S3FileStorage(String bucket, S3Client client, S3Presigner presigner) {
        this.bucket = bucket;
        this.client = client;
        this.presigner = presigner;
    }

    @Override
    public void save(String key, byte[] content) {
        client.putObject(PutObjectRequest.builder().bucket(bucket).key(key).build(), RequestBody.fromBytes(content));
    }

    @Override
    public byte[] load(String key) {
        var get = GetObjectRequest.builder().bucket(bucket).key(key).build();
        var signed = presigner.presignGetObject(GetObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(5)).getObjectRequest(get).build());
        var request = HttpRequest.newBuilder(URI.create(signed.url().toExternalForm()))
                .timeout(Duration.ofSeconds(60)).GET().build();
        try {
            var response = http.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("S3 file request failed with status " + response.statusCode());
            }
            return response.body();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("S3 file request interrupted", exception);
        }
    }

    @Override
    public void delete(String key) {
        client.deleteObject(request -> request.bucket(bucket).key(key));
    }

    @PreDestroy
    void close() {
        presigner.close();
        client.close();
        http.close();
    }
}
