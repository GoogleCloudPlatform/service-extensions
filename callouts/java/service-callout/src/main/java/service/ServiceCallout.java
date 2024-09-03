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


import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingRequest;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.ExternalProcessorGrpc;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
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
 * ServiceCallout is an abstract class representing a service callout server that can handle various stages of HTTP request/response processing.
 */
public class ServiceCallout {
    private static final Logger logger = Logger.getLogger(ServiceCallout.class.getName());

    private Server server;

    public ServiceCallout() {
        this(null, null, null, null, null, null, null, null, null, null, null, null, null);
    }

    public ServiceCallout(
            String ip,
            Integer port,
            Integer insecurePort,
            String healthCheckIp,
            Integer healthCheckPort,
            String healthCheckPath,
            Boolean serperateHealthCheck,
            byte[] cert,
            String certPath,
            byte[] certKey,
            String certKeyPath,
            Integer serverThreadCount,
            Boolean enableInsecurePort) {
        if (ip != null) {
            this.ip = ip;
        }
        if (port != null) {
            this.port = port;
        }
        if (insecurePort != null) {
            this.insecurePort = insecurePort;
        }
        if (healthCheckIp != null) {
            this.healthCheckIp = healthCheckIp;
        }
        if (healthCheckPort != null) {
            this.healthCheckPort = healthCheckPort;
        }
        if (healthCheckPath != null) {
            this.healthCheckPath = healthCheckPath;
        }
        if (serperateHealthCheck != null) {
            this.serperateHealthCheck = serperateHealthCheck;
        }
        if (certPath != null) {
            this.certPath = certPath;
        }

        if (cert != null) {
            this.cert = cert;
        } else {
            this.cert = readFileToBytes(this.certPath);
        }

        if (certKeyPath != null) {
            this.certKeyPath = certKeyPath;
        }

        if (certKey != null) {
            this.certKey = certKey;
        } else {
            this.certKey = readFileToBytes(this.certKeyPath);
        }

        if (serverThreadCount != null) {
            this.serverThreadCount = serverThreadCount;
        }
        if (enableInsecurePort != null) {
            this.enableInsecurePort = enableInsecurePort;
        }
    }

    private String ip = "0.0.0.0";
    private int port = 8443;
    private int insecurePort = 8443;
    private String healthCheckIp = "0.0.0.0";
    private int healthCheckPort = 8000;
    private String healthCheckPath = "/";
    private boolean serperateHealthCheck = false;
    private byte[] cert = null;
    private String certPath = "certs/server.crt";
    private byte[] certKey = null;
    private String certKeyPath = "certs/pkcs8_key.pem";
    private int serverThreadCount = 2;
    private boolean enableInsecurePort = true;

    /**
     * Starts the service callout server.
     * @throws IOException If an I/O error occurs while starting the server
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

        server = serverBuilder.addService(new ExternalProcessorImpl()).build().start();
        logger.info("Server started, listening on " + port);
        Runtime.getRuntime()
                .addShutdownHook(
                        new Thread() {
                            @Override
                            public void run() {
                                // Use stderr here since the logger may have been reset by its JVM shutdown hook.
                                logger.info("*** shutting down gRPC server since JVM is shutting down");
                                try {
                                    ServiceCallout.this.stop();
                                } catch (InterruptedException e) {
                                    e.printStackTrace(System.err);
                                }
                                logger.info("*** server shut down");
                            }
                        });
    }

    /**
     * Stops the service callout server.
     * @throws InterruptedException If interrupted while waiting for the server to shut down
     */
    private void stop() throws InterruptedException {
        if (server != null) {
            server.shutdown().awaitTermination(30, TimeUnit.SECONDS);
        }
    }

    /**
     * Await termination on the main thread since the grpc library uses daemon threads.
     * @throws InterruptedException If interrupted while waiting for the server to shut down
     */
    public void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }
    }

    /**
     * Processes a given request and returns the corresponding response.
     * @param request The request to be processed
     * @return The response to the processed request
     */
    public ProcessingResponse processRequest(ProcessingRequest request) {
        ProcessingResponse.Builder builder = ProcessingResponse.newBuilder();

        switch (request.getRequestCase()) {
            case REQUEST_HEADERS:
                Optional<HeadersOrImmediateResponse> response = onRequestHeaders(request.getRequestHeaders());
                if (response.isPresent()) {
                    HeadersOrImmediateResponse headersOrImmediateResponse = response.get();
                    if (headersOrImmediateResponse.isImmediateResponse()) {
                        builder.setImmediateResponse(headersOrImmediateResponse.getImmediateResponse());
                    } else {
                        builder.setRequestHeaders(headersOrImmediateResponse.getHeadersResponse());
                    }
                }
                break;
            case RESPONSE_HEADERS:
                onResponseHeaders(builder.getResponseHeadersBuilder(), request.getResponseHeaders());
                break;
            case REQUEST_BODY:
                onRequestBody(builder.getRequestBodyBuilder(), request.getRequestBody());
                break;
            case RESPONSE_BODY:
                onResponseBody(builder.getResponseBodyBuilder(), request.getResponseBody());
                break;
            case REQUEST_TRAILERS:
                break;
            case RESPONSE_TRAILERS:
                break;
            case REQUEST_NOT_SET:
            default:
                logger.log(Level.WARNING, "Received a ProcessingRequest with no request data.");
                break;
        }

        return builder.build();
    }

    /**
     * Callback method invoked upon receiving request headers.
     *
     * @param headers Incoming request headers
     * @return Optional HeadersOrImmediateResponse
     */
    public Optional<HeadersOrImmediateResponse> onRequestHeaders(HttpHeaders headers) {
        return Optional.empty();
    }

    /**
     * Callback method invoked upon receiving response headers.
     *
     * @param headerResponse Builder for modifying response headers
     * @param headers        Incoming response headers
     */
    public void onResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
        // Default implementation does nothing
    }

    /**
     * Callback method invoked upon receiving request body.
     *
     * @param bodyResponse Builder for modifying response body
     * @param body         Incoming request body
     */
    public void onRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        // Default implementation does nothing
    }

    /**
     * Callback method invoked upon receiving response body.
     *
     * @param bodyResponse Builder for modifying response body
     * @param body         Incoming response body
     */
    public void onResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        // Default implementation does nothing
    }

    /**
     * Implementation of gRPC service for processing requests.
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