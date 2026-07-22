package com.oneclicktrip.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

class FastApiAgentClientIntegrationTest {
    private final ObjectMapper objectMapper = new ObjectMapper();
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void springClientAndFastApiRunContractStayCompatible() throws Exception {
        AtomicReference<JsonNode> received = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/agent/runs", exchange -> respondToRun(exchange, received));
        server.start();

        String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
        FastApiAgentClient client = new FastApiAgentClient(
                RestClient.builder().baseUrl(baseUrl).build(),
                objectMapper
        );

        JsonNode response = client.run("conversation-contract", "42", "规划成都三日游", true);

        assertThat(received.get().path("conversation_id").asText()).isEqualTo("conversation-contract");
        assertThat(received.get().path("user_id").asText()).isEqualTo("42");
        assertThat(received.get().path("message").asText()).isEqualTo("规划成都三日游");
        assertThat(received.get().path("ignore_user_preferences").asBoolean()).isTrue();
        assertThat(response.path("intent").asText()).isEqualTo("trip_plan");
        assertThat(response.path("next_action").asText()).isEqualTo("planning_flow");
    }

    private void respondToRun(HttpExchange exchange, AtomicReference<JsonNode> received) throws IOException {
        received.set(objectMapper.readTree(exchange.getRequestBody()));
        byte[] payload = """
                {
                  "conversation_id": "conversation-contract",
                  "intent": "trip_plan",
                  "next_action": "planning_flow",
                  "checkpoint_version": 1,
                  "message_count": 1
                }
                """.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(200, payload.length);
        exchange.getResponseBody().write(payload);
        exchange.close();
    }
}
