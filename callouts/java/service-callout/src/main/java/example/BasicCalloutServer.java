package example;

import service.ServiceCallout;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;

import java.io.IOException;

public class BasicCalloutServer extends ServiceCallout {
    @Override
    public HeadersResponse OnRequestHeaders(HttpHeaders headers) {
        return null;
    }

    @Override
    public HeadersResponse OnResponseHeaders(HttpHeaders headers) {
        return null;
    }

    @Override
    public BodyResponse OnRequestBody(HttpBody body) {
        return null;
    }

    @Override
    public BodyResponse OnResponseBody(HttpBody body) {
        return null;
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new BasicCalloutServer();
        server.start();
        server.blockUntilShutdown();
    }

}
