package service;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.assertNotNull;

public class ServiceCalloutToolsTest {

    private HeadersResponse.Builder headerResponseBuilder;
    private BodyResponse.Builder bodyResponseBuilder;

    @Before
    public void setUp() {
        headerResponseBuilder = HeadersResponse.newBuilder();
        bodyResponseBuilder = BodyResponse.newBuilder();
    }

    @Test
    public void testAddHeaderMutations() {
        ServiceCalloutTools.addHeaderMutations(headerResponseBuilder, null);

        HeadersResponse response = headerResponseBuilder.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testConfigureHeadersResponse() {
        HeadersResponse response = ServiceCalloutTools.configureHeadersResponse(headerResponseBuilder, null, null,
                true);

        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testAddBodyMutationsResponse() {
        BodyResponse response = ServiceCalloutTools.AddBodyMutations(bodyResponseBuilder, null, null, null);

        assertNotNull(response);
        assertNotNull(response.getResponse());
    }
}
