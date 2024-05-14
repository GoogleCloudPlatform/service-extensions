package example;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableListMultimap;
import service.ServiceCallout;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;

import java.io.IOException;

import static service.ServiceCalloutTools.AddHeaderMutations;
import static service.ServiceCalloutTools.BuildBodyMutationResponse;
import static service.ServiceCalloutTools.ConfigureHeadersResponse;

public class BasicCalloutServer extends ServiceCallout {
    @Override
    public void OnRequestHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
        AddHeaderMutations(
                headerResponse, ImmutableListMultimap.of("request-header", "added", "c", "d").entries());
        ConfigureHeadersResponse(headerResponse, null, null, true);
    }

    @Override
    public void OnResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
        AddHeaderMutations(
                headerResponse, ImmutableListMultimap.of("response-header", "added", "c", "d").entries());
        ConfigureHeadersResponse(headerResponse, null, ImmutableList.of("c"), false);
    }

    @Override
    public void OnRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        BuildBodyMutationResponse(bodyResponse, "body added", null, null);
    }

    @Override
    public void OnResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        BuildBodyMutationResponse(bodyResponse, "body replaced", true, null);
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new BasicCalloutServer();
        server.start();
        server.blockUntilShutdown();
    }

}
