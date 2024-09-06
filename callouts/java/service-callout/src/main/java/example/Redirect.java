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
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.envoyproxy.envoy.type.v3.HttpStatus;
import io.envoyproxy.envoy.type.v3.StatusCode;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.io.IOException;

/**
 * Example callout server that performs an HTTP 301 redirect.
 * <p>
 * This class demonstrates how to handle a request header callout and return an immediate 301 redirect response
 * with a specified "Location" header. It modifies the {@link ProcessingResponse} to include the redirect status
 * and relevant headers.
 */
public class Redirect extends ServiceCallout {

    /**
     * Handles request headers and triggers an immediate HTTP 301 redirect.
     * <p>
     * This method sets up a response that includes the status code 301 (Moved Permanently) and the "Location" header
     * with a value of "http://service-extensions.com/redirect", signaling the client to redirect to this URL.
     *
     * @param processingResponseBuilder the {@link ProcessingResponse.Builder} used to construct the immediate response.
     * @param headers                   the {@link HttpHeaders} representing the incoming request headers (not modified).
     */
    @Override
    public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder,
                                 HttpHeaders headers) {

        // Define redirect headers using ImmutableMap
        ImmutableMap<String, String> redirectHeaders = ImmutableMap.of(
                "Location", "http://service-extensions.com/redirect"
        );

        // Prepare the status for 301 redirect
        HttpStatus status = HttpStatus.newBuilder().setCode(StatusCode.forNumber(301)).build();

        // Modify the ImmediateResponse.Builder directly using the updated method
        ServiceCalloutTools.buildImmediateResponse(
                processingResponseBuilder.getImmediateResponseBuilder(),
                status,
                redirectHeaders,
                null,  // No headers to remove in this case
                null   // No body for the response
        );
    }

    /**
     * Starts the callout server and listens for incoming gRPC requests.
     * <p>
     * The server will remain active until interrupted or terminated.
     *
     * @param args command-line arguments (not used).
     * @throws IOException if an I/O error occurs during server startup.
     * @throws InterruptedException if the server is interrupted while running.
     */
    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new Redirect();
        server.start();
        server.blockUntilShutdown();
    }
}
