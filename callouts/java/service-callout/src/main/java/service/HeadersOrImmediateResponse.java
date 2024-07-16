package service;

import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.ImmediateResponse;

/**
 * Represents either a HeadersResponse or an ImmediateResponse.
 */
public class HeadersOrImmediateResponse {
    private final HeadersResponse headersResponse;
    private final ImmediateResponse immediateResponse;

    private HeadersOrImmediateResponse(HeadersResponse headersResponse, ImmediateResponse immediateResponse) {
        this.headersResponse = headersResponse;
        this.immediateResponse = immediateResponse;
    }

    public static HeadersOrImmediateResponse ofHeaders(HeadersResponse headersResponse) {
        return new HeadersOrImmediateResponse(headersResponse, null);
    }

    public static HeadersOrImmediateResponse ofImmediate(ImmediateResponse immediateResponse) {
        return new HeadersOrImmediateResponse(null, immediateResponse);
    }

    public boolean isImmediateResponse() {
        return immediateResponse != null;
    }

    public HeadersResponse getHeadersResponse() {
        return headersResponse;
    }

    public ImmediateResponse getImmediateResponse() {
        return immediateResponse;
    }
}
