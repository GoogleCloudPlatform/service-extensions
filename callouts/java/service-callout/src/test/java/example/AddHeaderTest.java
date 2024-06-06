package example;

import example.add_header.AddHeader;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;

import java.lang.reflect.Method;

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

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
