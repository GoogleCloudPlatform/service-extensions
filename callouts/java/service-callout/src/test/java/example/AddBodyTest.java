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
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.lang.reflect.Method;


public class AddBodyTest {

    private AddBody server;

    @Before
    public void setUp() throws Exception {
        ServiceCallout.Builder builder = new ServiceCallout.Builder();

        server = new AddBody(builder);

        server.start();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Set the body content
        String bodyContent = "New body content";

        // Call the body mutation utility
        ServiceCalloutTools.addBodyMutations(
                processingResponseBuilder.getRequestBodyBuilder(),
                bodyContent,
                false,
                true
        );

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert the response
        Truth.assertThat(response).isNotNull();
        Truth.assertThat(response.getRequestBody().getResponse().getBodyMutation().getBody())
                .isEqualTo(ByteString.copyFromUtf8(bodyContent));

        Truth.assertThat(response.getRequestBody().getResponse().getClearRouteCache()).isTrue();
    }

    @Test
    public void testOnResponseBody() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Call the body mutation utility to clear the body
        ServiceCalloutTools.addBodyMutations(
                processingResponseBuilder.getResponseBodyBuilder(),
                null,  // No body content
                true,  // Clear the body
                false  // Do not clear route cache
        );

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert the response
        Truth.assertThat(response).isNotNull();
        Truth.assertThat(response.getResponseBody().getResponse().getBodyMutation().getClearBody()).isTrue();

        Truth.assertThat(response.getResponseBody().getResponse().getClearRouteCache()).isFalse();
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
