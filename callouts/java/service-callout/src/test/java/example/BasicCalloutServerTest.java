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

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.truth.extensions.proto.ProtoTruth;
import com.google.protobuf.ByteString;
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
import service.ServiceCalloutTools;

import java.lang.reflect.Method;

public class BasicCalloutServerTest {

    private TestServiceCallout server;

    @Before
    public void setUp(){
        server = new TestServiceCallout.Builder()
                .build();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    private static class TestServiceCallout extends ServiceCallout {

        public TestServiceCallout(TestServiceCallout.Builder builder) {
            super(builder);
        }

        public static class Builder extends ServiceCallout.Builder<Builder> {
            @Override
            public TestServiceCallout build() {
                return new TestServiceCallout(this);
            }

            @Override
            protected Builder self() {
                return this;
            }
        }

        @Override
        public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {
            // Example mutation: Add specific headers and clear route cache
            ServiceCalloutTools.addHeaderMutations(
                    processingResponseBuilder.getRequestHeadersBuilder(),
                    ImmutableMap.of("test-request-header", "test-value", "x", "y").entrySet(),
                    null, // No headers to remove
                    true, // Clear route cache
                    null  // No append action
            );
        }

        @Override
        public void onResponseHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {
            // Example mutation: Add and remove headers without clearing route cache
            ServiceCalloutTools.addHeaderMutations(
                    processingResponseBuilder.getResponseHeadersBuilder(),
                    ImmutableMap.of("test-response-header", "response-value").entrySet(),
                    ImmutableList.of("remove-header"),
                    false, // Do not clear route cache
                    null   // No append action
            );
        }

        @Override
        public void onRequestBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
            // Example mutation: Append "-added-body" to the request body
            String originalBody = body.getBody().toStringUtf8();
            String modifiedBody = originalBody + "-added-body";
            ServiceCalloutTools.addBodyMutations(
                    processingResponseBuilder.getRequestBodyBuilder(),
                    modifiedBody,
                    null,
                    null
            );
        }

        @Override
        public void onResponseBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
            // Example mutation: Replace response body with "test-replaced-body"
            ServiceCalloutTools.addBodyMutations(
                    processingResponseBuilder.getResponseBodyBuilder(),
                    "test-replaced-body",
                    null,
                    null
            );
        }
    }

    @Test
    public void testOnRequestHeaders() {
        // Create a ProcessingResponse.Builder
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Create a sample HttpHeaders object
        HttpHeaders requestHeaders = HttpHeaders.newBuilder()
                .setEndOfStream(false)
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
                                                                                .setKey("test-request-header")
                                                                                .setRawValue(ByteString.copyFromUtf8("test-value"))
                                                                                .build())
                                                                        .build())
                                                                .addSetHeaders(HeaderValueOption.newBuilder()
                                                                        .setHeader(HeaderValue.newBuilder()
                                                                                .setKey("x")
                                                                                .setRawValue(ByteString.copyFromUtf8("y"))
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

        // Create a sample HttpHeaders object
        HttpHeaders responseHeaders = HttpHeaders.newBuilder()
                .setEndOfStream(false)
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
                                                                                .setKey("test-response-header")
                                                                                .setRawValue(ByteString.copyFromUtf8("response-value"))
                                                                                .build())
                                                                        .build())
                                                                .addRemoveHeaders("remove-header")
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
                                                                .setBody(ByteString.copyFromUtf8("test-replaced-body"))
                                                )
                                                .setClearRouteCache(false)
                                )
                )
                .build();

        // Assert that the actual response matches the expected response
        ProtoTruth.assertThat(response).isEqualTo(expectedResponse);
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
