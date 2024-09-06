/*
 * Copyright (c) 2024 Google, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package example;

import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import service.ServiceCallout;

import static service.ServiceCalloutTools.addBodyMutations;

/**
 * A simple gRPC callout server that demonstrates HTTP body manipulation.
 * <p>
 * This class provides two key operations:
 * <ul>
 *     <li>On request body callout: Appends '-added-body' to the incoming request body.</li>
 *     <li>On response body callout: Replaces the outgoing response body with a static value 'body replaced'.</li>
 * </ul>
 * <p>
 * These operations illustrate how to modify HTTP request and response bodies in a gRPC-based service callout.
 */
public class AddBody extends ServiceCallout {

    /**
     * Constructor that accepts a ServiceCallout builder.
     * Passes the builder to the superclass (ServiceCallout) for configuration.
     *
     * @param builder The ServiceCallout builder used for custom server configuration.
     */
    public AddBody(ServiceCallout.Builder builder) {
        super(builder);
    }

    /**
     * Handles the request body by appending a custom suffix to the existing body.
     * <p>
     * The method appends "-added-body" to the original HTTP request body without clearing it.
     *
     * @param processingResponseBuilder the builder used to construct the {@link ProcessingResponse}.
     * @param body the {@link HttpBody} object representing the original request body.
     */
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
        AddBody server = new AddBody(builder);

        // Start the server and block until shutdown
        server.start();
        server.blockUntilShutdown();
    }
}
