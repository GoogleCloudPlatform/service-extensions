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

import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.service.ext_proc.v3.ExternalProcessorGrpc;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingRequest;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.grpc.Channel;
import io.grpc.Grpc;
import io.grpc.ManagedChannel;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.TlsChannelCredentials;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.StreamObserver;
import java.io.File;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/** A simple client that requests a greeting from the {@link HelloWorldServerTls} with TLS. */
public class ServiceCalloutTest {
  private static final Logger logger = Logger.getLogger(ServiceCalloutTest.class.getName());

  private final ExternalProcessorGrpc.ExternalProcessorStub stub;
  private static boolean recieved_response = false;

  StreamObserver<ProcessingResponse> responseObserver =
      new StreamObserver<ProcessingResponse>() {
        @Override
        public void onNext(ProcessingResponse value) {
          // Your callback to be executed whenever a TestResponse is received
          logger.log(Level.INFO, "Recieved Response: {0}", value.toString());
        }

        @Override
        public void onError(Throwable t) {
          Status status = Status.fromThrowable(t);
          String description = status.getDescription();
          Status.Code code = status.getCode();
          logger.log(Level.WARNING, "Response failed: {0}, {1}", new Object[] {code, description});
        }

        @Override
        public void onCompleted() {
          logger.log(Level.INFO, "Response completed.");
        }
      };

  // StreamObserver<ProcessingRequest> requestObserver =
  //     new StreamObserver<ProcessingRequest>() {
  //       @Override
  //       public void onNext(ProcessingRequest value) {

  //       }

  //       @Override
  //       public void onError(Throwable t) {
  //         Status status = Status.fromThrowable(t);
  //         String description = status.getDescription();
  //         Status.Code code = status.getCode();
  //         logger.log(Level.WARNING, "Request failed: {0}, {1}", new Object[] {code,
  // description});
  //       }

  //       @Override
  //       public void onCompleted() {
  //         logger.log(Level.INFO, "Request completed.");
  //       }
  //     };

  // // this cast is always safe
  // ClientCallStreamObserver<TestRequest> outboundObserver =
  //   (ClientCallStreamObserver) testServiceStub
  //       .testBidiStreaming(inboundObserver);

  // while (!outboundObserver.isReady()) {
  //   // application thread is free to block.
  //   // onReadyHandler() is a better approach than this naive sleep
  //   Thread.sleep(100);
  // }
  // // send the message
  // outboundObserver.onNext(TestRequest.newBuilder().build());

  // // send a trailer with an OK status
  // outboundObserver.onCompleted();

  /** Construct client for accessing RouteGuide server using the existing channel. */
  public ServiceCalloutTest(Channel channel) {
    stub = ExternalProcessorGrpc.newStub(channel);
  }

  public void setupStream() {
    logger.info("Setting up RPC bi-directional stream.");
    try {
      ClientCallStreamObserver<ProcessingRequest> requestObserver =
          (ClientCallStreamObserver<ProcessingRequest>) stub.process(responseObserver);
      while (!requestObserver.isReady()) {
        Thread.sleep(100);
      }
      logger.info("RequestObserver ready.");
      requestObserver.onNext(
          ProcessingRequest.newBuilder()
              .setRequestHeaders(
                  HttpHeaders.newBuilder().build())
              .build());
      logger.info("Sent request.");
      requestObserver.onCompleted();
    } catch (StatusRuntimeException e) {
      logger.log(Level.WARNING, "RPC failed: {0}", e.getStatus());
      return;
    } catch (InterruptedException e) {
      logger.log(Level.WARNING, "RPC failed: {0}", e.getMessage());
      return;
    }
  }

  /**
   * Greet server. If provided, the first element of {@code args} is the name to use in the
   * greeting.
   */
  public static void main(String[] args) throws Exception {

    if (args.length < 2 || args.length == 4 || args.length > 5) {
      System.out.println(
          "USAGE: HelloWorldClientTls host port [trustCertCollectionFilePath"
              + " [clientCertChainFilePath clientPrivateKeyFilePath]]\n"
              + "  Note: clientCertChainFilePath and clientPrivateKeyFilePath are only needed if"
              + " mutual auth is desired.");
      System.exit(0);
    }

    // If only defaults are necessary, you can use TlsChannelCredentials.create()
    // instead of
    // interacting with the Builder.
    TlsChannelCredentials.Builder tlsBuilder = TlsChannelCredentials.newBuilder();
    switch (args.length) {
      case 5:
        tlsBuilder.keyManager(new File(args[3]), new File(args[4]));
        // fallthrough
      case 3:
        tlsBuilder.trustManager(new File(args[2]));
        // fallthrough
      default:
    }
    String host = args[0];
    int port = Integer.parseInt(args[1]);
    ManagedChannel channel =
        Grpc.newChannelBuilderForAddress(host, port, tlsBuilder.build())
            .enableRetry()
            .keepAliveTime(10, TimeUnit.SECONDS)
            .build();
    logger.log(Level.INFO, "{0} {1} {2}", new Object[] {channel.toString(), host, port});
    try {
      ServiceCalloutTest client = new ServiceCalloutTest(channel);
      client.setupStream();
    } finally {
      channel.shutdown().awaitTermination(10, TimeUnit.SECONDS);
    }
  }
}
