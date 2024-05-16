package service;

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

import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;

import java.util.Map;


/**
 * ServiceCalloutTools provides utility methods for handling HTTP header and body mutations in service callouts.
 */
public class ServiceCalloutTools {

    /**
     * Adds header mutations to the response builder.
     * @param headersResponseBuilder Builder for modifying response headers
     * @param add Iterable containing header key-value pairs to be added
     */
    public static void AddHeaderMutations(
            HeadersResponse.Builder headersResponseBuilder, Iterable<Map.Entry<String, String>> add) {
        if (add != null) {
            HeaderMutation.Builder headerMutationBuilder =
                    headersResponseBuilder.getResponseBuilder().getHeaderMutationBuilder();
            for (Map.Entry<String, String> entry : add) {
                headerMutationBuilder
                        .addSetHeadersBuilder()
                        .getHeaderBuilder()
                        .setKey(entry.getKey())
                        .setValue(entry.getValue())
                        .setRawValue(ByteString.copyFromUtf8(entry.getValue()));
            }
        }
    }

    /**
     * Configures the headers response.
     * @param headersResponseBuilder Builder for modifying response headers
     * @param add Iterable containing header value options to be added
     * @param remove Iterable containing header keys to be removed
     * @param clearRouteCache Boolean indicating whether to clear the route cache
     * @return Constructed HeadersResponse object
     */
    public static HeadersResponse ConfigureHeadersResponse(
            HeadersResponse.Builder headersResponseBuilder,
            Iterable<HeaderValueOption> add,
            Iterable<String> remove,
            Boolean clearRouteCache) {
        CommonResponse.Builder responseBuilder = headersResponseBuilder.getResponseBuilder();
        HeaderMutation.Builder headerBuilder = responseBuilder.getHeaderMutationBuilder();
        if (add != null) {
            headerBuilder.addAllSetHeaders(add);
        }
        if (remove != null) {
            headerBuilder.addAllRemoveHeaders(remove);
        }
        if (clearRouteCache != null) {
            responseBuilder.setClearRouteCache(clearRouteCache);
        }
        return headersResponseBuilder.build();
    }

    /**
     * Builds a body mutation response.
     * @param bodyResponseBuilder Builder for modifying response body
     * @param body The body content to be set
     * @param clearBody Boolean indicating whether to clear the body
     * @param clearRouteCache Boolean indicating whether to clear the route cache
     * @return Constructed BodyResponse object
     */
    public static BodyResponse BuildBodyMutationResponse(
            BodyResponse.Builder bodyResponseBuilder,
            String body,
            Boolean clearBody,
            Boolean clearRouteCache) {
        CommonResponse.Builder responseBuilder = bodyResponseBuilder.getResponseBuilder();
        BodyMutation.Builder bodyBuilder = responseBuilder.getBodyMutationBuilder();
        if (body != null) {
            bodyBuilder.setBody(ByteString.copyFromUtf8(body));
        }
        if (clearBody != null) {
            bodyBuilder.setClearBody(clearBody);
        }
        if (clearRouteCache != null) {
            responseBuilder.setClearRouteCache(clearRouteCache);
        }
        return bodyResponseBuilder.build();
    }


}
