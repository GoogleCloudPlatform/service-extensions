/*
 * Copyright (c) 2024 Google, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package service;

import io.envoyproxy.envoy.service.ext_proc.v3.ExternalProcessorGrpc;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingRequest;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;
import io.grpc.netty.NettyServerBuilder;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.security.GeneralSecurityException;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;

import static utils.SslUtils.createSslContext;
import static utils.SslUtils.readFileToBytes;

/**
 * ServiceCallout provides a base class for handling HTTP request and response processing
 * in a gRPC-based service callout server. It processes incoming requests and modifies headers,
 * bodies, or immediate responses as per the service logic.
 */
public class ServiceCallout {
    private static final Logger logger = Logger.getLogger(ServiceCallout.class.getName());

    private Server server;
    private Server plaintextServer;
    private HttpServer healthCheckServer;
    private String ip;
    private int securePort;
    private int plaintextPort;
    private String healthCheckIp;
    private int healthCheckPort;
    private String healthCheckPath;
    private boolean combinedHealthCheck;
    private byte[] cert;
    private String certPath;
    private byte[] certKey;
    private String certKeyPath;
    private int serverThreadCount;
    private boolean enablePlainTextPort;
    private boolean enableTls;

    protected ServiceCallout(Builder<?> builder) {
        this.ip = Optional.ofNullable(builder.ip).orElse("0.0.0.0");
        this.securePort = Optional.ofNullable(builder.securePort).orElse(443); // Only used if enableTls is true
        this.plaintextPort = Optional.ofNullable(builder.plaintextPort).orElse(8080);
        this.healthCheckIp = Optional.ofNullable(builder.healthCheckIp).orElse("0.0.0.0");
        this.healthCheckPort = Optional.ofNullable(builder.healthCheckPort).orElse(80);
        this.healthCheckPath = Optional.ofNullable(builder.healthCheckPath).orElse("/");
        this.combinedHealthCheck = Optional.ofNullable(builder.combinedHealthCheck).orElse(false);

        // Handle cert path and cert data
        this.certPath = Optional.ofNullable(builder.certPath).orElse("certs/server.crt");
        this.cert = Optional.ofNullable(builder.cert)
                .orElseGet(() -> readFileToBytes(this.certPath)); // Read using final path

        // Handle cert key path and cert key data
        this.certKeyPath = Optional.ofNullable(builder.certKeyPath).orElse("certs/pkcs8_key.pem");
        this.certKey = Optional.ofNullable(builder.certKey)
                .orElseGet(() -> readFileToBytes(this.certKeyPath)); // Read using final path

        this.serverThreadCount = Optional.ofNullable(builder.serverThreadCount).orElse(2);
        this.enablePlainTextPort = Optional.ofNullable(builder.enablePlainTextPort).orElse(true);
        this.enableTls = Optional.ofNullable(builder.enableTls).orElse(false);

        // Initialize health check server if enabled
        if (!this.combinedHealthCheck) {
            try {
                initHealthCheckServer();
            } catch (IOException e) {
                logger.log(Level.SEVERE, "Failed to initialize Health Check Server", e);
                throw new RuntimeException(e);
            }
        }
    }

    // Builder class using Generics
    public static class Builder<T extends Builder<T>> {
        private String ip;
        private Integer securePort;
        private Integer plaintextPort;
        private String healthCheckIp;
        private Integer healthCheckPort;
        private String healthCheckPath;
        private Boolean combinedHealthCheck;
        private byte[] cert;
        private String certPath;
        private byte[] certKey;
        private String certKeyPath;
        private Integer serverThreadCount;
        private Boolean enablePlainTextPort;
        private Boolean enableTls;

        public T setIp(String ip) {
            this.ip = ip;
            return self();
        }

        public T setSecurePort(Integer securePort) {
            this.securePort = securePort;
            return self();
        }

        public T setPlaintextPort(Integer plaintextPort) {
            this.plaintextPort = plaintextPort;
            return self();
        }

        public T setHealthCheckIp(String healthCheckIp) {
            this.healthCheckIp = healthCheckIp;
            return self();
        }

        public T setHealthCheckPort(Integer healthCheckPort) {
            this.healthCheckPort = healthCheckPort;
            return self();
        }

        public T setHealthCheckPath(String healthCheckPath) {
            this.healthCheckPath = healthCheckPath;
            return self();
        }

        public T setCombinedHealthCheck(Boolean combinedHealthCheck) {
            this.combinedHealthCheck = combinedHealthCheck;
            return self();
        }

        public T setCert(byte[] cert) {
            this.cert = cert;
            return self();
        }

        public T setCertPath(String certPath) {
            this.certPath = certPath;
            return self();
        }

        public T setCertKey(byte[] certKey) {
            this.certKey = certKey;
            return self();
        }

        public T setCertKeyPath(String certKeyPath) {
            this.certKeyPath = certKeyPath;
            return self();
        }

        public T setServerThreadCount(Integer serverThreadCount) {
            this.serverThreadCount = serverThreadCount;
            return self();
        }

        public T setEnablePlainTextPort(Boolean enablePlainTextPort) {
            this.enablePlainTextPort = enablePlainTextPort;
            return self();
        }

        public T setEnableTls(Boolean enableTls) {
            this.enableTls = enableTls;
            return self();
        }

        // Return type is generic to allow subclass builders to work correctly
        protected T self() {
            return (T) this;
        }

        public ServiceCallout build() throws GeneralSecurityException, IOException {
            return new ServiceCallout(this);
        }
    }

    /**
     * Initializes the Health Check Server.
     *
     * @throws IOException If an error occurs while creating the server.
     */
    private void initHealthCheckServer() throws IOException {
        healthCheckServer = HttpServer.create(new InetSocketAddress(healthCheckIp, healthCheckPort), 0);
        healthCheckServer.createContext(healthCheckPath, new HealthCheckHandler());
        healthCheckServer.setExecutor(Executors.newFixedThreadPool(1)); // Single-threaded executor
    }

    /**
     * Starts the gRPC server that handles processing requests from Envoy.
     * Depending on the provided SSL configuration, the server will start in either secure or
     * insecure mode.
     *
     * @throws IOException If an error occurs while starting the server.
     */
    public void start() throws IOException {
        ExternalProcessorImpl processor = new ExternalProcessorImpl();

        if (enableTls && cert != null && certKey != null) {
            logger.info("Secure server starting...");

            server = NettyServerBuilder.forPort(securePort)
                    .sslContext(createSslContext(cert, certKey))
                    .addService(processor)
                    .executor(Executors.newFixedThreadPool(serverThreadCount)) // Configurable thread pool
                    .build()
                    .start();

            logger.info("Secure Server started, listening on " + securePort);

        }
        if (enablePlainTextPort) {
            logger.info("Plaintext server starting...");

            plaintextServer = ServerBuilder.forPort(plaintextPort)
                    .addService(processor)
                    .executor(Executors.newFixedThreadPool(serverThreadCount)) // Configurable thread pool
                    .build()
                    .start();

            logger.info("Plaintext Server started, listening on " + plaintextPort);
        }



        // Start Health Check Server if enabled
        if (!combinedHealthCheck) {
            healthCheckServer.start();
            logger.info("Health Check Server started, listening on " + healthCheckIp + ":" + healthCheckPort + " at path " + healthCheckPath);
        }

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            logger.info("*** shutting down gRPC server since JVM is shutting down");
            try {
                ServiceCallout.this.stop();
            } catch (InterruptedException e) {
                e.printStackTrace(System.err);
            }
            logger.info("*** server shut down");
        }));
    }

    /**
     * Stops the gRPC server gracefully.
     * This method will attempt to shut down the server within a 30-second timeout.
     *
     * @throws InterruptedException If the shutdown process is interrupted.
     */
    private void stop() throws InterruptedException {
        if (server != null) {
            server.shutdown().awaitTermination(30, TimeUnit.SECONDS);
        }

        if (plaintextServer != null) {
            plaintextServer.shutdown().awaitTermination(30, TimeUnit.SECONDS);
        }

        if (!combinedHealthCheck && healthCheckServer != null) {
            healthCheckServer.stop(0); // 0 delay for immediate stop
            logger.info("Health Check Server stopped.");
        }
    }

    /**
     * Blocks the main thread until the server is terminated.
     * This is necessary because gRPC uses daemon threads by default.
     *
     * @throws InterruptedException If interrupted while waiting for the server to shut down.
     */
    public void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }

        if (plaintextServer != null) {
            plaintextServer.awaitTermination();
        }
    }

    /**
     * Processes incoming {@link ProcessingRequest} and builds the corresponding {@link ProcessingResponse}.
     * This method handles different types of requests (headers, body) and delegates to specific
     * handlers for processing.
     *
     * @param request The request to be processed.
     * @return The processed response.
     */
    public ProcessingResponse processRequest(ProcessingRequest request) {
        ProcessingResponse.Builder builder = ProcessingResponse.newBuilder();

        switch (request.getRequestCase()) {
            case REQUEST_HEADERS:
                onRequestHeaders(builder, request.getRequestHeaders());
                break;
            case RESPONSE_HEADERS:
                onResponseHeaders(builder, request.getResponseHeaders());
                break;
            case REQUEST_BODY:
                onRequestBody(builder, request.getRequestBody());
                break;
            case RESPONSE_BODY:
                onResponseBody(builder, request.getResponseBody());
                break;
            case REQUEST_NOT_SET:
            default:
                logger.log(Level.WARNING, "Received a ProcessingRequest with no request data.");
                break;
        }

        return builder.build();
    }

    /**
     * Handles incoming request headers and allows for modification or response generation.
     *
     * @param processingResponseBuilder The response builder for modifying the response.
     * @param headers                   The incoming HTTP request headers.
     */
    public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder,HttpHeaders headers) {
    }

    /**
     * Handles incoming response headers and allows for modification or response generation.
     *
     * @param processingResponseBuilder The response builder for modifying the response.
     * @param headers                   The incoming HTTP response headers.
     */
    public void onResponseHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {
    }

    /**
     * Handles incoming request body and allows for modification or response generation.
     *
     * @param processingResponseBuilder The response builder for modifying the response.
     * @param body                      The incoming HTTP request body.
     */
    public void onRequestBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
    }

    /**
     * Handles incoming response body and allows for modification or response generation.
     *
     * @param processingResponseBuilder The response builder for modifying the response.
     * @param body                      The incoming HTTP response body.
     */
    public void onResponseBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
    }

    /**
     * gRPC service implementation that handles the processing of requests and sending of responses.
     */
    private class ExternalProcessorImpl extends ExternalProcessorGrpc.ExternalProcessorImplBase {

        @Override
        public StreamObserver<ProcessingRequest> process(
                final StreamObserver<ProcessingResponse> responseObserver) {
            return new StreamObserver<ProcessingRequest>() {
                @Override
                public void onNext(ProcessingRequest request) {
                    responseObserver.onNext(processRequest(request));
                }

                @Override
                public void onError(Throwable t) {
                    logger.log(Level.WARNING, "Encountered error in routeChat", t);
                }

                @Override
                public void onCompleted() {
                    responseObserver.onCompleted();
                }
            };
        }
    }

    /**
     * Health Check Handler responds with a simple "OK" message to indicate the server is healthy.
     */
    private static class HealthCheckHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String response = "OK";
            exchange.sendResponseHeaders(200, response.length());
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response.getBytes());
            }
        }
    }
}
