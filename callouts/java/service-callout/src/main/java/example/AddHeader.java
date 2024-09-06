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
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import service.ServiceCallout;

import static service.ServiceCalloutTools.addHeaderMutations;

/**
 * A gRPC-based service callout example that demonstrates HTTP header manipulation.
 * <p>
 * This class modifies headers in both request and response scenarios:
 * <ul>
 *     <li>For request headers: Adds new headers and clears the route cache.</li>
 *     <li>For response headers: Adds new headers, removes existing headers, and keeps the route cache intact.</li>
 * </ul>
 */
public class AddHeader extends ServiceCallout {

    /**
     * Constructor that accepts a ServiceCallout builder.
     * Passes the builder to the superclass (ServiceCallout) for configuration.
     *
     * @param builder The ServiceCallout builder used for custom server configuration.
     */
    public AddHeader(ServiceCallout.Builder builder) {
        super(builder);
    }

    /**
     * Modifies the incoming request headers by adding specific key-value pairs.
     * <p>
     * This method appends two headers, "request-header" with the value "added-request" and "c" with "d",
     * while clearing the route cache to ensure the new route is calculated.
     *
     * @param processingResponseBuilder the builder used to construct the {@link ProcessingResponse}.
     * @param headers the {@link HttpHeaders} representing the original request headers.
     */
    @Override
    public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder,
                                 HttpHeaders headers) {

        // Modify headers for the request
        addHeaderMutations(
                processingResponseBuilder.getRequestHeadersBuilder(),
                ImmutableMap.of("request-header", "added-request", "c", "d").entrySet(),  // Headers to add
                null,  // No headers to remove
                true,  // Clear route cache
                null   // No append action
        );
    }

    /**
     * Modifies the outgoing response headers by adding new headers and removing existing ones.
     * <p>
     * This method appends two headers, "response-header" with the value "added-response" and "c" with "d",
     * while removing the "foo" header. It does not clear the route cache.
     *
     * @param processingResponseBuilder the builder used to construct the {@link ProcessingResponse}.
     * @param headers the {@link HttpHeaders} representing the original response headers.
     */
    @Override
    public void onResponseHeaders(ProcessingResponse.Builder processingResponseBuilder,
                                  HttpHeaders headers) {
        // Modify headers for the response
        addHeaderMutations(
                processingResponseBuilder.getResponseHeadersBuilder(),
                ImmutableMap.of("response-header", "added-response", "c", "d").entrySet(),  // Headers to add
                ImmutableList.of("foo"),  // Headers to remove
                false,  // Do not clear route cache
                null  // No append action
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
        AddHeader server = new AddHeader(builder);

        // Start the server and block until shutdown
        server.start();
        server.blockUntilShutdown();
    }
}
