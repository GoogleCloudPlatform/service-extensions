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
import com.google.common.truth.Truth;
import com.google.common.truth.extensions.proto.ProtoTruth;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.lang.reflect.Method;

public class AddHeaderTest {

    private AddHeader server;

    @Before
    public void setUp() {
        server = new AddHeader();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestHeaders() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Define headers to add
        ImmutableMap<String, String> headersToAdd = ImmutableMap.of(
                "request-header", "added-request",
                "c", "d"
        );

        // Call the header mutation utility
        ServiceCalloutTools.addHeaderMutations(
                processingResponseBuilder.getRequestHeadersBuilder(),
                headersToAdd.entrySet(),
                null,
                true,
                null
        );

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert the response
        Truth.assertThat(response).isNotNull();
        ProtoTruth.assertThat(response.getRequestHeaders().getResponse().getHeaderMutation().getSetHeadersList())
                .containsExactly(
                        HeaderValueOption.newBuilder()
                                .setHeader(HeaderValue.newBuilder()
                                        .setKey("request-header")
                                        .setRawValue(ByteString.copyFromUtf8("added-request"))
                                        .build())
                                .build(),
                        HeaderValueOption.newBuilder()
                                .setHeader(HeaderValue.newBuilder()
                                        .setKey("c")
                                        .setRawValue(ByteString.copyFromUtf8("d"))
                                        .build())
                                .build()
                );

        Truth.assertThat(response.getRequestHeaders().getResponse().getClearRouteCache()).isTrue();
    }

    @Test
    public void testOnResponseHeaders() {
        ProcessingResponse.Builder processingResponseBuilder = ProcessingResponse.newBuilder();

        // Call the response header mutation utility without adding any headers
        ServiceCalloutTools.addHeaderMutations(
                processingResponseBuilder.getResponseHeadersBuilder(),
                null,
                ImmutableList.of("some-header-to-remove"),
                false,
                null
        );

        // Build the ProcessingResponse
        ProcessingResponse response = processingResponseBuilder.build();

        // Assert the response
        Truth.assertThat(response).isNotNull();
        Truth.assertThat(response.getResponseHeaders().getResponse().getHeaderMutation().getRemoveHeadersList())
                .containsExactly("some-header-to-remove");

        Truth.assertThat(response.getResponseHeaders().getResponse().getClearRouteCache()).isFalse();
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
