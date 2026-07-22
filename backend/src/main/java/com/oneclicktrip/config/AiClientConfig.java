package com.oneclicktrip.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Duration;

@Configuration
public class AiClientConfig {
    @Bean("aiRestClient")
    public RestClient aiRestClient(
            RestClientBuilderConfigurer configurer,
            @Value("${AI_SERVICE_BASE_URL:http://127.0.0.1:8000}") String baseUrl,
            @Value("${AI_SERVICE_CONNECT_TIMEOUT:3s}") Duration connectTimeout,
            @Value("${AI_SERVICE_READ_TIMEOUT:120s}") Duration readTimeout
    ) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);

        RestClient.Builder builder = configurer.configure(RestClient.builder());
        return builder
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();
    }
}
