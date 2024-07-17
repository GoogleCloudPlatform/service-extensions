package example;

import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.HeadersOrImmediateResponse;
import service.ServiceCallout;

import java.lang.reflect.Method;
import java.util.Optional;

import static org.junit.Assert.*;

public class AddHeaderTest {

    private AddHeader server;

    @Before
    public void setUp() {
        server = new AddHeader();
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

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
