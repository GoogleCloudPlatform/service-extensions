package service;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;

public class HealthCheckServer {

    private final int port;
    private final String path;
    private final String ip;
    private HttpServer server;

    public HealthCheckServer(int port, String path, String ip) {
        this.port = port;
        this.path = path;
        this.ip = ip;
    }

    public void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress(ip, port), 0);
        server.createContext(path, new HealthHandler());
        server.setExecutor(null); // creates a default executor
        server.start();
    }

    public void shutdown() {
        if (server != null) {
            server.stop(30); // Gracefully stop the server with 30 seconds delay
        }
    }

    static class HealthHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String response = "Server is healthy!";
            exchange.sendResponseHeaders(200, response.length());
            OutputStream os = exchange.getResponseBody();
            os.write(response.getBytes());
            os.close();
        }
    }

    public static void main(String[] args) throws IOException {
        HealthCheckServer healthCheckServer = new HealthCheckServer(8080, "/", "0.0.0.0");
        healthCheckServer.start();
    }
}