package com.hiremate.file.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

class S3FileStorageTests {

    @Test
    void storesAndReadsAnObjectUsingSignedUrl() throws Exception {
        AtomicReference<byte[]> saved = new AtomicReference<>();
        AtomicReference<String> readQuery = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/bucket/company/file", exchange -> {
            if ("PUT".equals(exchange.getRequestMethod())) {
                saved.set(exchange.getRequestBody().readAllBytes());
                exchange.sendResponseHeaders(200, -1);
            } else {
                readQuery.set(exchange.getRequestURI().getRawQuery());
                byte[] content = saved.get();
                exchange.sendResponseHeaders(200, content.length);
                exchange.getResponseBody().write(content);
            }
            exchange.close();
        });
        server.start();
        URI endpoint = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
        var credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create("test", "test"));
        var config = S3Configuration.builder().pathStyleAccessEnabled(true).chunkedEncodingEnabled(false).build();
        try (S3Client client = S3Client.builder().endpointOverride(endpoint).region(Region.AP_NORTHEAST_2)
                .credentialsProvider(credentials).serviceConfiguration(config).build();
                S3Presigner presigner = S3Presigner.builder().endpointOverride(endpoint).region(Region.AP_NORTHEAST_2)
                        .credentialsProvider(credentials).serviceConfiguration(config).build()) {
            var storage = new S3FileStorage("bucket", client, presigner);
            byte[] content = "private document".getBytes(StandardCharsets.UTF_8);

            storage.save("company/file", content);

            assertThat(storage.load("company/file")).isEqualTo(content);
            assertThat(readQuery.get()).contains("X-Amz-Signature=");
        } finally {
            server.stop(0);
        }
    }
}
