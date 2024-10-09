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
package service;

import com.google.common.collect.ImmutableMap;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;
import io.envoyproxy.envoy.type.v3.HttpStatus;

import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * ServiceCalloutTools provides utility methods for handling HTTP header and body mutations in
 * Envoy service callouts. These methods are used to construct responses by adding, removing,
 * and modifying headers and bodies, as well as setting HTTP status codes.
 */
public class ServiceCalloutTools {

    private static final Logger logger = Logger.getLogger(ServiceCalloutTools.class.getName());

    /**
     * Adds and removes HTTP headers, with optional route cache clearing.
     * <p>
     * This method allows headers to be added, removed, and optionally appends header values.
     * The response can also be configured to clear the route cache.
     *
     * @param headersResponseBuilder The {@link HeadersResponse.Builder} used to build the response.
     * @param addHeaders             A map of header key-value pairs to be added to the response.
     * @param removeHeaders          A list of header keys to be removed from the response.
     * @param clearRouteCache        If true, clears the route cache after applying header changes.
     * @param appendAction           Optional action specifying how to append headers (e.g., replace or append).
     */
    public static void addHeaderMutations(
            HeadersResponse.Builder headersResponseBuilder,
            Iterable<Map.Entry<String, String>> addHeaders,
            Iterable<String> removeHeaders,
            Boolean clearRouteCache,
            HeaderValueOption.HeaderAppendAction appendAction) {

        // Access or initialize HeaderMutation
        HeaderMutation.Builder headerMutationBuilder =
                headersResponseBuilder.getResponseBuilder().getHeaderMutationBuilder();

        // Handle adding headers
        if (addHeaders != null) {
            for (Map.Entry<String, String> entry : addHeaders) {
                HeaderValueOption.Builder headerValueOptionBuilder = HeaderValueOption.newBuilder()
                        .setHeader(HeaderValue.newBuilder()
                                .setKey(entry.getKey())
                                .setRawValue(ByteString.copyFromUtf8(entry.getValue()))
                        );

                // Apply append action if present
                if (appendAction != null) {
                    headerValueOptionBuilder.setAppendAction(appendAction);
                }

                // Add header mutation
                headerMutationBuilder.addSetHeaders(headerValueOptionBuilder.build());
            }
        }

        // Handle removing headers
        if (removeHeaders != null) {
            headerMutationBuilder.addAllRemoveHeaders(removeHeaders);
        }

        // Clear route cache if required
        if (Boolean.TRUE.equals(clearRouteCache)) {
            headersResponseBuilder.getResponseBuilder().setClearRouteCache(true);
        }
    }

    /**
     * Modifies the HTTP response body by setting or clearing the body content.
     * <p>
     * This method sets the body of the response, or clears the body if no content is provided.
     * Body and clearBody are mutually exclusive—if a body is provided, clearBody is ignored.
     *
     * @param bodyResponseBuilder The {@link BodyResponse.Builder} used to build the body response.
     * @param body                The body content to be set. If null, the body will not be modified.
     * @param clearBody           If true, clears the body when no body content is provided.
     * @param clearRouteCache     If true, clears the route cache after modifying the body.
     */
    public static void addBodyMutations(
            BodyResponse.Builder bodyResponseBuilder,
            String body,
            Boolean clearBody,
            Boolean clearRouteCache) {
        CommonResponse.Builder responseBuilder = bodyResponseBuilder.getResponseBuilder();
        BodyMutation.Builder bodyBuilder = responseBuilder.getBodyMutationBuilder();

        if (body != null) {
            // Set the body, ignore clearBody if body is provided
            bodyBuilder.setBody(ByteString.copyFromUtf8(body));

            // Log a warning if both body and clearBody are provided
            if (Boolean.TRUE.equals(clearBody)) {
                logger.log(Level.WARNING, "Body and clearBody are mutually exclusive. clearBody will be ignored.");
            }
        } else {
            // If body is not provided, use clearBody
            bodyBuilder.setClearBody(clearBody);
        }

        // Handle clearRouteCache if provided
        if (clearRouteCache != null) {
            responseBuilder.setClearRouteCache(clearRouteCache);
        }
    }

    /**
     * Builds an immediate HTTP response by setting the status, headers, and optional body.
     * <p>
     * This method modifies an {@link ImmediateResponse.Builder} to include an HTTP status,
     * header modifications, and optionally, a response body. Headers can be added and removed.
     *
     * @param builder        The {@link ImmediateResponse.Builder} to modify.
     * @param status         The {@link HttpStatus} representing the HTTP status code for the response.
     * @param headersToAdd   A map of header key-value pairs to be added to the response.
     * @param headersToRemove A list of header keys to be removed from the response.
     * @param body           Optional body content for the response. If null, the body will not be set.
     */
    public static void buildImmediateResponse(
            ImmediateResponse.Builder builder,
            HttpStatus status,
            ImmutableMap<String, String> headersToAdd,
            List<String> headersToRemove,
            String body) {

        // Set the HTTP status
        builder.setStatus(status);

        // Obtain HeaderMutation.Builder from the parent ImmediateResponse.Builder
        HeaderMutation.Builder headerMutationBuilder = builder.getHeadersBuilder();

        // Handle adding headers
        if (headersToAdd != null) {
            for (Map.Entry<String, String> entry : headersToAdd.entrySet()) {
                HeaderValueOption headerOption = HeaderValueOption.newBuilder()
                        .setHeader(HeaderValue.newBuilder()
                                .setKey(entry.getKey())
                                .setRawValue(ByteString.copyFromUtf8(entry.getValue()))
                                .build()
                        )
                        .build();

                headerMutationBuilder.addSetHeaders(headerOption);
            }
        }

        // Handle removing headers
        if (headersToRemove != null) {
            headerMutationBuilder.addAllRemoveHeaders(headersToRemove);
        }

        // Set the body if it is not null
        if (body != null) {
            builder.setBody(body);
        }
    }
}
