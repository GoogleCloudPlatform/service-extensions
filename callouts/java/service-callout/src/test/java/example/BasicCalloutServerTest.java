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
package example;

import com.google.common.truth.Truth;
import com.google.common.truth.extensions.proto.ProtoTruth;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderMap;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.TimeUnit;

public class BasicCalloutServerTest {

    private BasicCalloutServer server;

    @Before
    public void setUp() throws IOException {
        server = new BasicCalloutServer.Builder()
                .setHealthCheckPort(8000)
                .setHealthCheckPath("/health")
                .setCombinedHealthCheck(false)
                .build();

        server.start();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestHeaders() {
        // Create a ProcessingResponse.Builder
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Manually build HeaderMap with desired headers
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder()
                        .setKey("original-header")
                        .setValue("original-value")
                        .build())
                .build();

        // Create a sample HttpHeaders
        HttpHeaders requestHeaders = HttpHeaders.newBuilder()
                .setEndOfStream(false)
                .setHeaders(headerMap)
                .build();

        // Invoke the onRequestHeaders method
        server.onRequestHeaders(processingResponseBuilder, requestHeaders);

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Define the expected ProcessingResponse
        ProcessingResponse expectedResponse = ProcessingResponse.newBuilder()
                .setRequestHeaders(
                        HeadersResponse.newBuilder()
                                .setResponse(
                                        CommonResponse.newBuilder()
                                                .setHeaderMutation(
                                                        HeaderMutation.newBuilder()
                                                                .addSetHeaders(HeaderValueOption.newBuilder()
                                                                        .setHeader(HeaderValue.newBuilder()
                                                                                .setKey("request-header")
                                                                                .setRawValue(ByteString.copyFromUtf8("added-request"))
                                                                                .build())
                                                                        .build())
                                                                .addSetHeaders(HeaderValueOption.newBuilder()
                                                                        .setHeader(HeaderValue.newBuilder()
                                                                                .setKey("c")
                                                                                .setRawValue(ByteString.copyFromUtf8("d"))
                                                                                .build())
                                                                        .build())
                                                )
                                                .setClearRouteCache(true)
                                )
                )
                .build();

        // Assert that the actual response matches the expected response
        ProtoTruth.assertThat(response).isEqualTo(expectedResponse);
    }

    @Test
    public void testOnResponseHeaders() {
        // Create a ProcessingResponse.Builder
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Manually build HeaderMap with desired headers
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder()
                        .setKey("original-header")
                        .setValue("original-value")
                        .build())
                .build();

        // Create a sample HttpHeaders
        HttpHeaders responseHeaders = HttpHeaders.newBuilder()
                .setEndOfStream(false)
                .setHeaders(headerMap)
                .build();

        // Invoke the onResponseHeaders method
        server.onResponseHeaders(processingResponseBuilder, responseHeaders);

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Define the expected ProcessingResponse
        ProcessingResponse expectedResponse = ProcessingResponse.newBuilder()
                .setResponseHeaders(
                        HeadersResponse.newBuilder()
                                .setResponse(
                                        CommonResponse.newBuilder()
                                                .setHeaderMutation(
                                                        HeaderMutation.newBuilder()
                                                                .addSetHeaders(HeaderValueOption.newBuilder()
                                                                        .setHeader(HeaderValue.newBuilder()
                                                                                .setKey("response-header")
                                                                                .setRawValue(ByteString.copyFromUtf8("added-response"))
                                                                                .build())
                                                                        .build())
                                                                .addSetHeaders(HeaderValueOption.newBuilder()
                                                                        .setHeader(HeaderValue.newBuilder()
                                                                                .setKey("c")
                                                                                .setRawValue(ByteString.copyFromUtf8("d"))
                                                                                .build())
                                                                        .build())
                                                                .addRemoveHeaders("foo")
                                                )
                                                .setClearRouteCache(false)
                                )
                )
                .build();

        // Assert that the actual response matches the expected response
        ProtoTruth.assertThat(response).isEqualTo(expectedResponse);
    }

    @Test
    public void testOnRequestBody() {
        // Create a ProcessingResponse.Builder
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Define the original body content
        String originalBody = "OriginalBody";

        // Create a sample HttpBody object
        HttpBody requestBody = HttpBody.newBuilder()
                .setBody(ByteString.copyFromUtf8(originalBody))
                .setEndOfStream(false)
                .build();

        // Invoke the onRequestBody method
        server.onRequestBody(processingResponseBuilder, requestBody);

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Define the expected ProcessingResponse
        ProcessingResponse expectedResponse = ProcessingResponse.newBuilder()
                .setRequestBody(
                        BodyResponse.newBuilder()
                                .setResponse(
                                        CommonResponse.newBuilder()
                                                .setBodyMutation(
                                                        BodyMutation.newBuilder()
                                                                .setBody(ByteString.copyFromUtf8(originalBody + "-added-body"))
                                                                .build()
                                                )
                                                .setClearRouteCache(false)
                                )
                )
                .build();

        // Assert that the actual response matches the expected response
        ProtoTruth.assertThat(response).isEqualTo(expectedResponse);
    }

    @Test
    public void testOnResponseBody() {
        // Create a ProcessingResponse.Builder
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Create a sample HttpBody object
        HttpBody responseBody = HttpBody.newBuilder()
                .setBody(ByteString.copyFromUtf8("OriginalResponseBody"))
                .setEndOfStream(false)
                .build();

        // Invoke the onResponseBody method
        server.onResponseBody(processingResponseBuilder, responseBody);

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Define the expected ProcessingResponse
        ProcessingResponse expectedResponse = ProcessingResponse.newBuilder()
                .setResponseBody(
                        BodyResponse.newBuilder()
                                .setResponse(
                                        CommonResponse.newBuilder()
                                                .setBodyMutation(
                                                        BodyMutation.newBuilder()
                                                                .setBody(ByteString.copyFromUtf8("body replaced"))
                                                                .build()
                                                )
                                                .setClearRouteCache(false)
                                )
                )
                .build();

        // Assert that the actual response matches the expected response
        ProtoTruth.assertThat(response).isEqualTo(expectedResponse);
    }

    @Test
    public void testHealthCheck() throws Exception {
        // Define the health check URL
        String healthCheckUrl = "http://0.0.0.0:8000/health";

        // Wait briefly to ensure the health check server is up
        TimeUnit.SECONDS.sleep(1);

        // Create a URL object
        URL url = new URL(healthCheckUrl);

        // Open a connection
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();

        try {
            // Set request method to GET
            connection.setRequestMethod("GET");

            // Set a reasonable timeout
            connection.setConnectTimeout(3000); // 3 seconds
            connection.setReadTimeout(3000);    // 3 seconds

            // Connect and get the response code
            int responseCode = connection.getResponseCode();

            // Assert that the response code is 200 (OK)
            Truth.assertThat(responseCode).isEqualTo(200);

            // Read and assert the response body
            BufferedReader in = new BufferedReader(new InputStreamReader(connection.getInputStream()));
            String inputLine;
            StringBuilder responseContent = new StringBuilder();

            while ((inputLine = in.readLine()) != null) {
                responseContent.append(inputLine);
            }
            in.close();

            // Response body contains "OK"
            Truth.assertThat(responseContent.toString()).contains("OK");

        } finally {
            // Disconnect the connection
            connection.disconnect();
        }
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}