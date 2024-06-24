package example;

/*
 * Copyright 2024 The gRPC Authors
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


import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;
import io.envoyproxy.envoy.type.v3.HttpStatus;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.io.IOException;
import java.util.AbstractMap;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Example callout server.
 * <p>
 * Provides a non-comprehensive set of responses for each of the possible
 * callout interactions.
 * <p>
 * For request header callouts we provide a mutation to add a header
 * '{header-request: request}', remove a header 'foo', and to clear the
 * route cache. On response header callouts, we respond with a mutation to add
 * the header '{header-response: response}'.
 */
public class Redirect extends ServiceCallout {

    @Override
    public void OnRequestHeaders(ImmediateResponse.Builder immediateResponse, HttpHeaders headers) {
        List<Map.Entry<String, String>> redirectHeaders = Collections.singletonList(
                new AbstractMap.SimpleEntry<>("Location", "http://service-extensions.com/redirect")
        );

        // Generate the immediate response using a utility method
        ServiceCalloutTools.BuildImmediateResponse(
                immediateResponse,
                redirectHeaders,
                HttpStatus.newBuilder().setCodeValue(301).build()
        );
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new Redirect();
        server.start();
        server.blockUntilShutdown();
    }

}
