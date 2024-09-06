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
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import service.ServiceCallout;

import static service.ServiceCalloutTools.addBodyMutations;
import static service.ServiceCalloutTools.addHeaderMutations;

/**
 * Example callout server for processing HTTP headers and bodies.
 * <p>
 * This class handles several callout events and demonstrates how to mutate headers and bodies in both requests and responses.
 * It provides a basic implementation for:
 * <ul>
 *     <li>Request headers: Adds specific headers and clears the route cache.</li>
 *     <li>Response headers: Adds and removes specific headers without clearing the route cache.</li>
 *     <li>Request body: Appends content to the body.</li>
 *     <li>Response body: Replaces the body with a predefined value.</li>
 * </ul>
 */
public class BasicCalloutServer extends ServiceCallout {

    /**
     * Constructor that accepts a ServiceCallout builder.
     * Passes the builder to the superclass (ServiceCallout) for configuration.
     *
     * @param builder The ServiceCallout builder used for custom server configuration.
     */
    public BasicCalloutServer(ServiceCallout.Builder builder) {
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
     * Handles the request body by appending a custom suffix to the existing body.
     * <p>
     * The method appends "-added-body" to the original HTTP request body without clearing it.
     *
     * @param processingResponseBuilder the builder used to construct the {@link ProcessingResponse}.
     * @param body the {@link HttpBody} object representing the original request body.
     */
    @Override
    public void onRequestBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
        // Modify the body by appending "-added-body" and ensure no clearBody action
        addBodyMutations(processingResponseBuilder.getRequestBodyBuilder(), body.getBody().toStringUtf8() + "-added-body", null, null);
    }

    /**
     * Handles the response body by replacing it with a static value.
     * <p>
     * The method completely replaces the original response body with "body replaced".
     *
     * @param processingResponseBuilder the builder used to construct the {@link ProcessingResponse}.
     * @param body the {@link HttpBody} object representing the original response body.
     */
    @Override
    public void onResponseBody(ProcessingResponse.Builder processingResponseBuilder, HttpBody body) {
        // Replace the body with "body replaced"
        addBodyMutations(processingResponseBuilder.getResponseBodyBuilder(), "body replaced", null, null);
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
        BasicCalloutServer server = new BasicCalloutServer(builder);

        // Start the server and block until shutdown
        server.start();
        server.blockUntilShutdown();
    }

}
