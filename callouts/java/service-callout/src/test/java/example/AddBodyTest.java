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
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.io.IOException;
import java.lang.reflect.Method;


public class AddBodyTest {

    private AddBody server;

    @Before
    public void setUp() throws IOException {
        server = new AddBody.Builder()
                .setSecurePort(8443)
                .setHealthCheckPort(8000)
                .build();

        server.start();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestBody_EmptyBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Simulate an empty request body
        String emptyBodyContent = "";

        // Call the onRequestBody method
        server.onRequestBody(processingResponseBuilder, HttpBody.newBuilder().setBody(ByteString.copyFromUtf8(emptyBodyContent)).build());

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is not null and it appends the "-added-body" string
        Truth.assertThat(response.getRequestBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8("-added-body"));
    }

    @Test
    public void testOnResponseBody_FixedBodyReplacement() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Simulate a non-empty response body
        String originalBodyContent = "Original body content";

        // Call the onResponseBody method
        server.onResponseBody(processingResponseBuilder, HttpBody.newBuilder().setBody(ByteString.copyFromUtf8(originalBodyContent)).build());

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is replaced with "body replaced"
        Truth.assertThat(response.getResponseBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8("body replaced"));
    }

    @Test
    public void testOnRequestBody_NonEmptyBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Simulate a non-empty request body
        String bodyContent = "Original request content";

        // Call the onRequestBody method
        server.onRequestBody(processingResponseBuilder, HttpBody.newBuilder().setBody(ByteString.copyFromUtf8(bodyContent)).build());

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is modified by appending "-added-body"
        Truth.assertThat(response.getRequestBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8("Original request content-added-body"));
    }

    @Test
    public void testOnResponseBody_EmptyOriginalBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Simulate an empty response body
        String emptyBodyContent = "";

        // Call the onResponseBody method
        server.onResponseBody(processingResponseBuilder, HttpBody.newBuilder().setBody(ByteString.copyFromUtf8(emptyBodyContent)).build());

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is replaced with "body replaced"
        Truth.assertThat(response.getResponseBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8("body replaced"));
    }

    /**
     * This test verifies body mutations by directly calling the utility method without running through the server.
     */
    @Test
    public void testOnRequestBody_ClearBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Call the body mutation utility to clear the body
        ServiceCalloutTools.addBodyMutations(
                processingResponseBuilder.getRequestBodyBuilder(),
                null,  // No body content
                true,  // Clear the body
                true   // Clear the route cache
        );

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is cleared
        Truth.assertThat(response.getRequestBody().getResponse().getBodyMutation().getClearBody()).isTrue();
        Truth.assertThat(response.getRequestBody().getResponse().getClearRouteCache()).isTrue();
    }

    @Test
    public void testOnRequestBody_UnmodifiedBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Simulate a body that remains unchanged
        String bodyContent = "Body that should remain unchanged";

        // Do not call any mutation, simulating no modification
        server.onRequestBody(processingResponseBuilder, HttpBody.newBuilder().setBody(ByteString.copyFromUtf8(bodyContent)).build());

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert that the body is unchanged
        Truth.assertThat(response.getRequestBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8("Body that should remain unchanged-added-body"));
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
