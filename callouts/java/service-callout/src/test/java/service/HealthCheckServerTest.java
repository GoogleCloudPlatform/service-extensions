package service;

import static org.junit.Assert.assertEquals;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

public class HealthCheckServerTest {

    private HealthCheckServer healthCheckServer;

    @Before
    public void setUp() throws IOException {
        healthCheckServer = new HealthCheckServer(8080, "/", "0.0.0.0");
        healthCheckServer.start();
    }

    @After
    public void tearDown() {
        healthCheckServer.shutdown();
    }

    @Test
    public void testServerIsHealthy() throws IOException {
        URL url = new URL("http://localhost:8080/");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod("GET");
        connection.connect();

        int responseCode = connection.getResponseCode();
        assertEquals(200, responseCode);

        StringBuilder responseBuilder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                responseBuilder.append(line);
            }
        }

        String response = responseBuilder.toString();
        assertEquals("Server is healthy!", response);

        connection.disconnect();
    }
}
