package io.elmos.runner;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HealthProbe {
    private HealthProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].matches("http://127\\.0\\.0\\.1:[0-9]{2,5}/[A-Za-z0-9/_-]*")) {
            System.exit(64);
        }
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        HttpResponse<Void> response = client.send(
                HttpRequest.newBuilder(URI.create(args[0]))
                        .timeout(Duration.ofSeconds(3))
                        .GET()
                        .build(),
                HttpResponse.BodyHandlers.discarding()
        );
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            System.exit(1);
        }
    }
}
