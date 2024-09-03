package example;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.HeadersOrImmediateResponse;
import service.ServiceCallout;

import java.lang.reflect.Method;
import java.util.Optional;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.assertFalse;


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
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        Optional<HeadersOrImmediateResponse> response = server.onRequestHeaders(headers);
        HeadersResponse headersResponse = response.get().getHeadersResponse();

        assertNotNull(headersResponse);
        assertTrue(headersResponse.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("request-header")
                        && header.getHeader().getValue().equals("added-request")));
        assertTrue(headersResponse.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("c")
                        && header.getHeader().getValue().equals("d")));
        assertTrue(headersResponse.getResponse().getClearRouteCache());
    }

    @Test
    public void testOnResponseHeaders() {
        HeadersResponse.Builder headerResponse = HeadersResponse.newBuilder();
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        server.onResponseHeaders(headerResponse, headers);

        HeadersResponse response = headerResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
        assertFalse(response.getResponse().getClearRouteCache());
        assertTrue(response.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("response-header")
                        && header.getHeader().getValue().equals("added-response")));
        assertTrue(response.getResponse().getHeaderMutation().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("c")
                        && header.getHeader().getValue().equals("d")));
    }

    @Test
    public void testOnRequestBody() {
        BodyResponse.Builder bodyResponse = BodyResponse.newBuilder();
        HttpBody body = HttpBody.getDefaultInstance();

        server.onRequestBody(bodyResponse, body);

        BodyResponse response = bodyResponse.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testOnResponseBody() {
        BodyResponse.Builder bodyResponse = BodyResponse.newBuilder();
        HttpBody body = HttpBody.getDefaultInstance();

        server.onResponseBody(bodyResponse, body);

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
