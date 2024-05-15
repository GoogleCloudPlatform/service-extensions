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

import io.envoyproxy.envoy.service.ext_proc.v3.*;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;
import io.grpc.netty.NettyServerBuilder;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

import static utils.SslUtils.createSslContext;
import static utils.SslUtils.readFileToBytes;

/**
 * Server that manages startup/shutdown of a {@code Greeter} server.
 */
public abstract class ServiceCallout {
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
    private HealthCheckServer healthCheckServer;

    public void start() throws IOException {
        if (!serperateHealthCheck) {
            logger.info("Health check server starting...");
            healthCheckServer = new HealthCheckServer(healthCheckPort, healthCheckPath, healthCheckIp);
            healthCheckServer.start();
        }

        /* The port on which the server should run */
        ServerBuilder<?> serverBuilder;
        if (cert != null && certKey != null) {
            // If both certificate and private key are provided, start the server with SSL
            logger.info("Secure server starting...");
            serverBuilder = NettyServerBuilder.forPort(port)
                    .sslContext(createSslContext(cert, certKey));
        } else {
            // Otherwise, start the server without SSL
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
                                    stopHealthCheckServer();
                                    ServiceCallout.this.stop();
                                } catch (InterruptedException e) {
                                    e.printStackTrace(System.err);
                                }
                                logger.info("*** server shut down");
                            }
                        });
    }

    private void stop() throws InterruptedException {
        if (server != null) {
            server.shutdown().awaitTermination(30, TimeUnit.SECONDS);
        }
    }

    private void stopHealthCheckServer() throws InterruptedException {
        if (!serperateHealthCheck) {
            logger.info("*** shutting down health check server");
            healthCheckServer.shutdown();
        }
    }

    /**
     * Await termination on the main thread since the grpc library uses daemon threads.
     */
    public void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }
    }

    public ProcessingResponse ProcessRequest(ProcessingRequest request) {
        ProcessingResponse.Builder builder = ProcessingResponse.newBuilder();

        switch (request.getRequestCase()) {
            case REQUEST_HEADERS:
                OnRequestHeaders(builder.getRequestHeadersBuilder(), request.getRequestHeaders());
                break;
            case RESPONSE_HEADERS:
                OnResponseHeaders(builder.getRequestHeadersBuilder(), request.getResponseHeaders());
                break;
            case REQUEST_BODY:
                OnRequestBody(builder.getRequestBodyBuilder(), request.getRequestBody());
                break;
            case RESPONSE_BODY:
                OnResponseBody(builder.getResponseBodyBuilder(), request.getResponseBody());
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

    public abstract void OnRequestHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers);

    public abstract void OnResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers);

    public abstract void OnRequestBody(BodyResponse.Builder bodyResponse, HttpBody body);

    public abstract void OnResponseBody(BodyResponse.Builder bodyResponse, HttpBody body);

    private class ExternalProcessorImpl extends ExternalProcessorGrpc.ExternalProcessorImplBase {

        @Override
        public StreamObserver<ProcessingRequest> process(
                final StreamObserver<ProcessingResponse> responseObserver) {
            return new StreamObserver<ProcessingRequest>() {
                @Override
                public void onNext(ProcessingRequest request) {
                    responseObserver.onNext(ProcessRequest(request));
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