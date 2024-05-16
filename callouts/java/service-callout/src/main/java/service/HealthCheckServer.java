package service;

/*
 * Copyright 2015 The gRPC Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;

/**
 * HealthCheckServer is a simple HTTP server implementation designed to handle health check requests.
 */
public class HealthCheckServer {

    private final int port;
    private final String path;
    private final String ip;
    private HttpServer server;

    /**
     * Constructs a new HealthCheckServer with the specified parameters.
     * @param port The port on which the server listens
     * @param path The path to handle health check requests
     * @param ip The IP address on which the server binds
     */
    public HealthCheckServer(int port, String path, String ip) {
        this.port = port;
        this.path = path;
        this.ip = ip;
    }

    /**
     * Starts the HealthCheckServer.
     * @throws IOException If an I/O error occurs while starting the server
     */
    public void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress(ip, port), 0);
        server.createContext(path, new HealthHandler());
        server.setExecutor(null); // creates a default executor
        server.start();
    }

    /**
     * Shuts down the HealthCheckServer.
     */
    public void shutdown() {
        if (server != null) {
            server.stop(30); // Gracefully stop the server with 30 seconds delay
        }
    }

    /**
     * HealthHandler handles incoming HTTP requests for health checks.
     */
    static class HealthHandler implements HttpHandler {
        /**
         * Handles the HTTP request for health check.
         * @param exchange The HTTP exchange object representing the request and response
         * @throws IOException If an I/O error occurs while handling the request
         */
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String response = "Server is healthy!";
            exchange.sendResponseHeaders(200, response.length());
            OutputStream os = exchange.getResponseBody();
            os.write(response.getBytes());
            os.close();
        }
    }

    /**
     * Main method to start the HealthCheckServer.
     * @param args Command-line arguments (not used)
     * @throws IOException If an I/O error occurs while starting the server
     */
    public static void main(String[] args) throws IOException {
        HealthCheckServer healthCheckServer = new HealthCheckServer(8080, "/", "0.0.0.0");
        healthCheckServer.start();
    }
}