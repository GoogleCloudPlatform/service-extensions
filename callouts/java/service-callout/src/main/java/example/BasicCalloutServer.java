package example;

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


import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableListMultimap;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import service.ServiceCallout;

import java.io.IOException;

import static service.ServiceCalloutTools.*;

/**
 *  Example callout server.
 *
 *  Provides a non-comprehensive set of responses for each of the callout events.
 */
public class BasicCalloutServer extends ServiceCallout {
//    @Override
//    public void OnRequestHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
//        AddHeaderMutations(
//                headerResponse, ImmutableListMultimap.of("request-header", "added", "c", "d").entries());
//        ConfigureHeadersResponse(headerResponse, null, null, true);
//    }
//
//    @Override
//    public void OnResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
//        AddHeaderMutations(
//                headerResponse, ImmutableListMultimap.of("response-header", "added", "c", "d").entries());
//        ConfigureHeadersResponse(headerResponse, null, ImmutableList.of("c"), false);
//    }

    @Override
    public void onRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        AddBodyMutations(bodyResponse, "body added", null, null);
    }

    @Override
    public void onResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        AddBodyMutations(bodyResponse, "body replaced", true, null);
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new BasicCalloutServer();
        server.start();
        server.blockUntilShutdown();
    }

}
