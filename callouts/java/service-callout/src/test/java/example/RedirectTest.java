package example;

import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.HeadersOrImmediateResponse;
import service.ServiceCallout;

import java.lang.reflect.Method;
import java.util.Optional;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

public class RedirectTest {

    private Redirect server;

    @Before
    public void setUp() {
        server = new Redirect();
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    @Test
    public void testOnRequestHeaders() {
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        Optional<HeadersOrImmediateResponse> response = server.onRequestHeaders(headers);
        ImmediateResponse immediateResponse = response.get().getImmediateResponse();

        assertNotNull(response);
        assertTrue(immediateResponse.hasStatus());
        assertTrue(immediateResponse.getHeaders().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("Location")
                        && header.getHeader().getValue().equals("http://service-extensions.com/redirect")));
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
