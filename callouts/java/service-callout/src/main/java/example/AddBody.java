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

import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import service.ServiceCallout;

import java.io.IOException;

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
     * Starts the callout server and listens for incoming gRPC requests.
     * <p>
     * The server will remain active until interrupted or terminated.
     *
     * @param args command-line arguments (not used).
     * @throws IOException if an I/O error occurs during server startup.
     * @throws InterruptedException if the server is interrupted while running.
     */
    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new AddBody();
        server.start();
        server.blockUntilShutdown();
    }
}
