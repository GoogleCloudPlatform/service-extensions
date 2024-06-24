package example;

import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import service.ServiceCallout;

import java.lang.reflect.Method;

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
        ImmediateResponse.Builder immediateResponse = ImmediateResponse.newBuilder();
        HttpHeaders headers = HttpHeaders.getDefaultInstance();

        server.OnRequestHeaders(immediateResponse, headers);

        ImmediateResponse response = immediateResponse.build();
        assertNotNull(response);
        assertTrue(response.hasStatus());
        assertTrue(response.getHeaders().getSetHeadersList().stream()
                .anyMatch(header -> header.getHeader().getKey().equals("Location")
                        && header.getHeader().getValue().equals("http://service-extensions.com/redirect")));
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}
