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


import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableListMultimap;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import service.HeadersOrImmediateResponse;
import service.ServiceCallout;

import java.io.IOException;
import java.util.Optional;

import static service.ServiceCalloutTools.*;

/**
 *  Example callout server.
 *
 *  Provides a non-comprehensive set of responses for each of the possible
 *   callout interactions.
 *
 *   For request header callouts we provide a mutation to add a header
 *   '{header-request: request}', remove a header 'foo', and to clear the
 *   route cache. On response header callouts, we respond with a mutation to add
 *   the header '{header-response: response}'.
 */
public class AddHeader extends ServiceCallout {

    @Override
    public Optional<HeadersOrImmediateResponse> onRequestHeaders(HttpHeaders headers) {
        HeadersResponse.Builder headerResponseBuilder = HeadersResponse.newBuilder();
        HeadersResponse modifiedHeaders = addHeaderMutations(
                headerResponseBuilder, ImmutableListMultimap.of("request-header", "added-request", "c", "d").entries());
        HeadersResponse finalHeaders = configureHeadersResponse(modifiedHeaders.toBuilder(), null, null, true);

        return Optional.of(HeadersOrImmediateResponse.ofHeaders(finalHeaders));
    }

    @Override
    public void onResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
        HeadersResponse modifiedHeaders = addHeaderMutations(
                headerResponse, ImmutableListMultimap.of("response-header", "added-response", "c", "d").entries());
        HeadersResponse finalHeaders = configureHeadersResponse(modifiedHeaders.toBuilder(), null, ImmutableList.of("c"), false);
        headerResponse.mergeFrom(finalHeaders);
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new AddHeader();
        server.start();
        server.blockUntilShutdown();
    }



}
