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
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.ExternalProcessorGrpc;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingRequest;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.grpc.Grpc;
import io.grpc.Server;
import io.grpc.TlsServerCredentials;
import io.grpc.stub.StreamObserver;
import java.io.File;
import java.io.IOException;
import java.util.Map;
import java.util.Map.Entry;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Server that manages startup/shutdown of a {@code Greeter} server. */
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
  private String certPath = "../ssl_creds/localhost_public.pem";
  private Bytes certKey = null;
  private String certKeyPath = "../ssl_creds/localhost_private.pem";
  private int serverThreadCount = 2;
  private boolean enableInsecurePort = true;

  private Server healthCheckServer;

  // private void startHealthCheckServer() throws IOException {
  //   if (!serperateHealthCheck) {
  //     HealthStatusManager healthStatusManager = new HealthStatusManager();
  //     BindableService healthService = healthStatusManager.getHealthService();
  //     healthCheckServer =
  //         ServerBuilder.forPort(healthCheckPort).addService(healthService).build().start();
  //     healthStatusManager.setStatus("", ServingStatus.SERVING);
  //   }
  // }

  private void stopHealthCheckServer() throws InterruptedException {
    if (!serperateHealthCheck) {
      healthCheckServer.shutdown().awaitTermination(30, TimeUnit.SECONDS);
    }
  }

  public void start() throws IOException {
    /* The port on which the server should run */
    TlsServerCredentials.Builder tlsBuilder =
        TlsServerCredentials.newBuilder().keyManager(new File(certPath), new File(certKeyPath));

    // Setup the callout extension service.
    server =
        Grpc.newServerBuilderForPort(port, tlsBuilder.build())
            .addService(new ExternalProcessorImpl())
            .build()
            .start();

    // // Setup the health check service.
    // startHealthCheckServer();

    // Configure callout shutdown hook.
    logger.info("Server started, listening on " + port);
    Runtime.getRuntime()
        .addShutdownHook(
            new Thread() {
              @Override
              public void run() {
                // Use stderr here since the logger may have been reset by its JVM shutdown hook.
                System.err.println("*** shutting down gRPC server since JVM is shutting down");
                try {
                  stopHealthCheckServer();
                  ServiceCallout.this.stop();
                } catch (InterruptedException e) {
                  e.printStackTrace(System.err);
                }
                System.err.println("*** server shut down");
              }
            });
  }

  public void stop() throws InterruptedException {
    if (server != null) {
      server.shutdown().awaitTermination(30, TimeUnit.SECONDS);
    }
  }

  /** Await termination on the main thread since the grpc library uses daemon threads. */
  public void blockUntilShutdown() throws InterruptedException {
    if (server != null) {
      server.awaitTermination();
    }
  }

  public void AddHeaderMutations(
      HeadersResponse.Builder headersResponseBuilder, Iterable<Map.Entry<String, String>> add) {
    if (add != null) {
      HeaderMutation.Builder headerMutationBuilder =
          headersResponseBuilder.getResponseBuilder().getHeaderMutationBuilder();
      for (Entry<String, String> entry : add) {
        headerMutationBuilder
            .addSetHeadersBuilder()
            .getHeaderBuilder()
            .setKey(entry.getKey())
            .setRawValue(ByteString.copyFromUtf8(entry.getValue()));
      }
    }
  }

  public HeadersResponse ConfigureHeadersResponse(
      HeadersResponse.Builder headersResponseBuilder,
      Iterable<HeaderValueOption> add,
      Iterable<String> remove,
      Boolean clearRouteCache) {
    CommonResponse.Builder responseBuilder = headersResponseBuilder.getResponseBuilder();
    HeaderMutation.Builder headerBuilder = responseBuilder.getHeaderMutationBuilder();
    if (add != null) {
      headerBuilder.addAllSetHeaders(add);
    }
    if (remove != null) {
      headerBuilder.addAllRemoveHeaders(remove);
    }
    if (clearRouteCache != null) {
      responseBuilder.setClearRouteCache(clearRouteCache);
    }
    return headersResponseBuilder.build();
  }

  public BodyResponse BuildBodyMutationResponse(
      BodyResponse.Builder bodyResponseBuilder,
      String body,
      Boolean clearBody,
      Boolean clearRouteCache) {
    CommonResponse.Builder responseBuilder = bodyResponseBuilder.getResponseBuilder();
    BodyMutation.Builder bodyBuilder = responseBuilder.getBodyMutationBuilder();
    if (body != null) {
      bodyBuilder.setBody(ByteString.copyFromUtf8(body));
    }
    if (clearBody != null) {
      bodyBuilder.setClearBody(clearBody);
    }
    if (clearRouteCache != null) {
      responseBuilder.setClearRouteCache(clearRouteCache);
    }
    return bodyResponseBuilder.build();
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
        logger.log(Level.WARNING, "Receieved a ProcessingRequest with no request data.");
        break;
    }
    return builder.build();
  }

  public void OnRequestHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
    logger.log(Level.INFO, "Unhandled RequestHeader recieved, returning an empty HeadersResponse.");
  }

  public void OnResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
    logger.log(
        Level.INFO, "Unhandled ResponseHeaders recieved, returning an empty HeadersResponse.");
  }

  public void OnRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
    logger.log(Level.INFO, "Unhandled RequestBody recieved, returning an empty BodyResponse.");
  }

  public void OnResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
    logger.log(Level.INFO, "Unhandled ResponseBody recieved, returning an empty BodyResponse.");
  }

  /** Main launches the server from the command line. */
  public static void main(String[] args) throws IOException, InterruptedException {
    final ServiceCallout server = new ServiceCallout();
    server.start();
    server.blockUntilShutdown();
  }

  private class ExternalProcessorImpl extends ExternalProcessorGrpc.ExternalProcessorImplBase {

    @Override
    public StreamObserver<ProcessingRequest> process(
        final StreamObserver<ProcessingResponse> responseObserver) {
      // responseObserver.onCompleted();
      return new StreamObserver<ProcessingRequest>() {
        @Override
        public void onNext(ProcessingRequest request) {
          responseObserver.onNext(ProcessRequest(request));
        }

        @Override
        public void onError(Throwable t) {
          logger.log(Level.WARNING, "Encountered request error", t);
        }

        @Override
        public void onCompleted() {
          responseObserver.onCompleted();
        }
      };
    }
  }
}
