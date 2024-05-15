package service;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

import java.io.IOException;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import io.envoyproxy.envoy.service.ext_proc.v3.BodyMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.CommonResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeaderMutation;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;

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
        ServiceCalloutTools.AddHeaderMutations(headerResponseBuilder, null);

        HeadersResponse response = headerResponseBuilder.build();
        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testConfigureHeadersResponse() {
        HeadersResponse response = ServiceCalloutTools.ConfigureHeadersResponse(headerResponseBuilder, null, null,
                true);

        assertNotNull(response);
        assertNotNull(response.getResponse());
    }

    @Test
    public void testBuildBodyMutationResponse() {
        BodyResponse response = ServiceCalloutTools.BuildBodyMutationResponse(bodyResponseBuilder, null, null, null);

        assertNotNull(response);
        assertNotNull(response.getResponse());
    }
}
