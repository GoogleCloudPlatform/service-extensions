package example;

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

public class AddBodyTest {

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
