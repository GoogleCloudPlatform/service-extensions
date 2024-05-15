package example;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import service.ServiceCallout;

import java.lang.reflect.Method;

public class BasicCalloutServerTest {

    private BasicCalloutServer server;

    @Before
    public void setUp() {
        server = new BasicCalloutServer();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestHeaders() {
        HeadersResponse.Builder headerResponse = HeadersResponse.newBuilder();
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        server.OnRequestHeaders(headerResponse, headers);

        HeadersResponse response = headerResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
        assertTrue(response.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("request-header")
                        && header.getHeader().getValue().equals("added")));
        assertTrue(response.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("c")
                        && header.getHeader().getValue().equals("d")));
        assertTrue(response.getResponse().getClearRouteCache());
    }

    @Test
    public void testOnResponseHeaders() {
        HeadersResponse.Builder headerResponse = HeadersResponse.newBuilder();
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        server.OnResponseHeaders(headerResponse, headers);

        HeadersResponse response = headerResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
        assertFalse(response.getResponse().getClearRouteCache());
    }

    @Test
    public void testOnRequestBody() {
        BodyResponse.Builder bodyResponse = BodyResponse.newBuilder();
        HttpBody body = HttpBody.getDefaultInstance();

        server.OnRequestBody(bodyResponse, body);

        BodyResponse response = bodyResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testOnResponseBody() {
        BodyResponse.Builder bodyResponse = BodyResponse.newBuilder();
        HttpBody body = HttpBody.getDefaultInstance();

        server.OnResponseBody(bodyResponse, body);

        BodyResponse response = bodyResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
