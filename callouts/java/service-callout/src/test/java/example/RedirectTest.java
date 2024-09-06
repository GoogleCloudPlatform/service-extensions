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

import com.google.common.collect.ImmutableMap;
import com.google.common.truth.extensions.proto.ProtoTruth;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;
import io.envoyproxy.envoy.type.v3.HttpStatus;
import io.envoyproxy.envoy.type.v3.StatusCode;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.lang.reflect.Method;
import java.util.Collections;

public class RedirectTest {

    private Redirect server;

    @Before
    public void setUp() throws Exception {
        ServiceCallout.Builder builder = new ServiceCallout.Builder();

        server = new Redirect(builder);

        server.start();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    // Simulate building the ImmediateResponse using the utility method in ServiceCalloutTools.
    @Test
    public void testBuildImmediateResponseRedirect() {
        // Create the ImmediateResponse builder.
        ImmediateResponse.Builder immediateResponseBuilder = ImmediateResponse.newBuilder();

        // Use the buildImmediateResponse method from ServiceCalloutTools.
        ServiceCalloutTools.buildImmediateResponse(
                immediateResponseBuilder,
                HttpStatus.newBuilder().setCode(StatusCode.forNumber(301)).build(),
                ImmutableMap.of("Location", "http://service-extensions.com/redirect"),
                Collections.emptyList(),
                null
        );

        // Build the ImmediateResponse.
        ImmediateResponse response = immediateResponseBuilder.build();

        // Verify that the status is set correctly.
        ProtoTruth.assertThat(response.getStatus())
                .isEqualTo(HttpStatus.newBuilder().setCode(StatusCode.forNumber(301)).build());

        // Verify that the "Location" header is set correctly.
        ProtoTruth.assertThat(response.getHeaders().getSetHeadersList())
                .containsExactly(
                        HeaderValueOption.newBuilder()
                                .setHeader(HeaderValue.newBuilder()
                                        .setKey("Location")
                                        .setRawValue(ByteString.copyFromUtf8("http://service-extensions.com/redirect"))
                                        .build())
                                .build()
                );
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
