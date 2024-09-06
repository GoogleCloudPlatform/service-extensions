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

/**
 * Example callout server that performs an HTTP 301 redirect.
 * <p>
 * This class demonstrates how to handle a request header callout and return an immediate 301 redirect response
 * with a specified "Location" header. It modifies the {@link ProcessingResponse} to include the redirect status
 * and relevant headers.
 */
public class Redirect extends ServiceCallout {

    /**
     * Constructor that accepts a ServiceCallout builder.
     * Passes the builder to the superclass (ServiceCallout) for configuration.
     *
     * @param builder The ServiceCallout builder used for custom server configuration.
     */
    public Redirect(ServiceCallout.Builder builder) {
        super(builder);
    }

    /**
     * Handles request headers and triggers an immediate HTTP 301 redirect.
     * <p>
     * This method sets up a response that includes the status code 301 (Moved Permanently) and the "Location" header
     * with a value of "http://service-extensions.com/redirect", signaling the client to redirect to this URL.
     *
     * @param processingResponseBuilder the {@link ProcessingResponse.Builder} used to construct the immediate response.
     * @param headers                   the {@link HttpHeaders} representing the incoming request headers (not modified).
     */

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
     * Main method to start the gRPC callout server with a custom configuration
     * using the {@link ServiceCallout.Builder}.
     * <p>
     * This method initializes the server with default or custom configurations,
     * starts the server, and keeps it running until manually terminated.
     * The server processes incoming gRPC requests for HTTP manipulations.
     * </p>
     *
     * <p>Usage:</p>
     * <pre>{@code
     * ServiceCallout.Builder builder = new ServiceCallout.Builder()
     *     .setIp("111.222.333.444")       // Customize IP
     *     .setPort(8443)                  // Set the port for secure communication
     *     .setEnableInsecurePort(true)    // Enable an insecure communication port
     *     .setServerThreadCount(4);       // Set the number of server threads
     * }</pre>
     *
     * @param args Command-line arguments, not used in this implementation.
     * @throws Exception If an error occurs during server startup or shutdown.
     */
    public static void main(String[] args) throws Exception {
        // Create a builder for ServiceCallout with custom configuration
        ServiceCallout.Builder builder = new ServiceCallout.Builder();

        // Create AddBody server using the configured builder
        Redirect server = new Redirect(builder);

        // Start the server and block until shutdown
        server.start();
        server.blockUntilShutdown();
    }
}
