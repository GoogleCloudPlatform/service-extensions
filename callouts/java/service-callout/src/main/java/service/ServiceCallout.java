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
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

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
    private String ip = "0.0.0.0";
    private int port = 8443;
    private int insecurePort = 8443;
    private String healthCheckIp = "0.0.0.0";
    private int healthCheckPort = 8000;
    private String healthCheckPath = "/";
    private boolean separateHealthCheck = false;
    private byte[] cert = null;
    private String certPath = "certs/server.crt";
    private byte[] certKey = null;
    private String certKeyPath = "certs/pkcs8_key.pem";
    private int serverThreadCount = 2;
    private boolean enableInsecurePort = true;

    /**
     * Default constructor initializes the ServiceCallout with default server configurations.
     */
    public ServiceCallout() {
        this(null, null, null, null, null, null, null, null, null, null, null, null, null);
    }

    /**
     * Overloaded constructor allowing custom configuration for the server.
     *
     * @param ip                 The IP address to bind the server.
     * @param port               The secure port for the server.
     * @param insecurePort        The insecure port for the server.
     * @param healthCheckIp       The IP address for the health check.
     * @param healthCheckPort     The port for the health check.
     * @param healthCheckPath     The HTTP path for health checks.
     * @param separateHealthCheck Whether a separate health check service is enabled.
     * @param cert                The SSL certificate as a byte array.
     * @param certPath            The file path to the SSL certificate.
     * @param certKey             The private key for the SSL certificate as a byte array.
     * @param certKeyPath         The file path to the private key.
     * @param serverThreadCount   The number of threads to allocate for the server.
     * @param enableInsecurePort  If true, enables the insecure port.
     */
    public ServiceCallout(
            String ip,
            Integer port,
            Integer insecurePort,
            String healthCheckIp,
            Integer healthCheckPort,
            String healthCheckPath,
            Boolean separateHealthCheck,
            byte[] cert,
            String certPath,
            byte[] certKey,
            String certKeyPath,
            Integer serverThreadCount,
            Boolean enableInsecurePort) {

        this.ip = Optional.ofNullable(ip).orElse(this.ip);
        this.port = Optional.ofNullable(port).orElse(this.port);
        this.insecurePort = Optional.ofNullable(insecurePort).orElse(this.insecurePort);
        this.healthCheckIp = Optional.ofNullable(healthCheckIp).orElse(this.healthCheckIp);
        this.healthCheckPort = Optional.ofNullable(healthCheckPort).orElse(this.healthCheckPort);
        this.healthCheckPath = Optional.ofNullable(healthCheckPath).orElse(this.healthCheckPath);
        this.separateHealthCheck = Optional.ofNullable(separateHealthCheck).orElse(this.separateHealthCheck);
        this.certPath = Optional.ofNullable(certPath).orElse(this.certPath);
        this.cert = Optional.ofNullable(cert).orElseGet(() -> readFileToBytes(this.certPath));
        this.certKeyPath = Optional.ofNullable(certKeyPath).orElse(this.certKeyPath);
        this.certKey = Optional.ofNullable(certKey).orElseGet(() -> readFileToBytes(this.certKeyPath));
        this.serverThreadCount = Optional.ofNullable(serverThreadCount).orElse(this.serverThreadCount);
        this.enableInsecurePort = Optional.ofNullable(enableInsecurePort).orElse(this.enableInsecurePort);
    }

    /**
     * Starts the gRPC server that handles processing requests from Envoy.
     * Depending on the provided SSL configuration, the server will start in either secure or
     * insecure mode.
     *
     * @throws IOException If an error occurs while starting the server.
     */
    public void start() throws IOException {
        ServerBuilder<?> serverBuilder;

        if (cert != null && certKey != null) {
            logger.info("Secure server starting...");
            serverBuilder = NettyServerBuilder.forPort(port)
                    .sslContext(createSslContext(cert, certKey));
        } else {
            logger.info("Insecure server starting...");
            serverBuilder = ServerBuilder.forPort(port);
        }

        server = serverBuilder
                .addService(new ExternalProcessorImpl())
                .executor(java.util.concurrent.Executors.newFixedThreadPool(serverThreadCount)) // Configurable thread pool
                .build()
                .start();

        logger.info("Server started, listening on " + port);

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
}
