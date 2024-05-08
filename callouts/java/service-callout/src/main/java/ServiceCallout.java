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

import com.google.common.primitives.Bytes;
import io.envoyproxy.envoy.api.v2.core.HeaderMap;
import io.envoyproxy.envoy.api.v2.route.RouteAction;
import io.envoyproxy.envoy.service.ext_proc.v3.*;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Server that manages startup/shutdown of a {@code Greeter} server.
 */
public class ServiceCallout {
    private static final Logger logger = Logger.getLogger(ServiceCallout.class.getName());

    private Server server;

    public ServiceCallout() {
        this(null, null, null, null, null, null, null, null, null, null, null, null);
    }

    public ServiceCallout(
            String ip,
            Integer port,
            Integer insecurePort,
            String healthCheckIp,
            Integer healthCheckPort,
            Boolean serperateHealthCheck,
            Bytes cert,
            String certPath,
            Bytes certKey,
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
        if (serperateHealthCheck != null) {
            this.serperateHealthCheck = serperateHealthCheck;
        }
        if (cert != null) {
            this.cert = cert;
        }
        if (certPath != null) {
            this.certPath = certPath;
        }
        if (certKey != null) {
            this.certKey = certKey;
        }
        if (certKeyPath != null) {
            this.certKeyPath = certKeyPath;
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
    private boolean serperateHealthCheck = false;
    private Bytes cert = null;
    private String certPath = "../ssl_creds/localhost.crt";
    private Bytes certKey = null;
    private String certKeyPath = "../ssl_creds/localhost.key";
    private int serverThreadCount = 2;
    private boolean enableInsecurePort = true;

    private void start() throws IOException {
        /* The port on which the server should run */
        server = ServerBuilder.forPort(port).addService(new ExternalProcessorImpl()).build().start();
        logger.info("Server started, listening on " + port);
        Runtime.getRuntime()
                .addShutdownHook(
                        new Thread() {
                            @Override
                            public void run() {
                                // Use stderr here since the logger may have been reset by its JVM shutdown hook.
                                System.err.println("*** shutting down gRPC server since JVM is shutting down");
                                try {
                                    ServiceCallout.this.stop();
                                } catch (InterruptedException e) {
                                    e.printStackTrace(System.err);
                                }
                                System.err.println("*** server shut down");
                            }
                        });
    }

    private void stop() throws InterruptedException {
        if (server != null) {
            server.shutdown().awaitTermination(30, TimeUnit.SECONDS);
        }
    }

    /**
     * Await termination on the main thread since the grpc library uses daemon threads.
     */
    private void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }
    }

    public ProcessingResponse ProcessRequest(ProcessingRequest request) {

        ProcessingResponse response = ProcessingResponse.newBuilder().build();
        return response;
    }

    public HeadersResponse OnRequestHeaders(HttpHeaders headers) {
        return null;
    }

    public HeadersResponse OnResponseHeaders(HttpHeaders headers) {
        return null;
    }

    public BodyResponse OnRequestBody(HttpBody body) {
        return null;
    }

    public BodyResponse OnResponseBody(HttpBody body) {
        return null;
    }

    /**
     * Main launches the server from the command line.
     */
    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new ServiceCallout();
        server.start();
        server.blockUntilShutdown();
    }

    private class ExternalProcessorImpl extends ExternalProcessorGrpc.ExternalProcessorImplBase {

        @Override
        public StreamObserver<ProcessingRequest> process(
                final StreamObserver<ProcessingResponse> responseObserver) {
            return new StreamObserver<ProcessingRequest>() {
                @Override
                public void onNext(ProcessingRequest note) {
                    ProcessRequest(note);
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