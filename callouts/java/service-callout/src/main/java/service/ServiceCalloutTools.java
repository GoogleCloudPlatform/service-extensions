package service;

import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderValueOption;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;

import java.util.Map;

public class ServiceCalloutTools {

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
