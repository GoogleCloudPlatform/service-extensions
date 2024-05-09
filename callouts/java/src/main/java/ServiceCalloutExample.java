import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableListMultimap;
import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import java.io.IOException;

/*
 * Copyright 2015 The gRPC Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

public class ServiceCalloutExample extends ServiceCallout {
  @Override
  public void OnRequestHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
    AddHeaderMutations(
        headerResponse, ImmutableListMultimap.of("request-header", "added", "c", "d").entries());
    ConfigureHeadersResponse(headerResponse, null, null, true);
  }

  @Override
  public void OnResponseHeaders(HeadersResponse.Builder headerResponse, HttpHeaders headers) {
    AddHeaderMutations(
        headerResponse, ImmutableListMultimap.of("response-header", "added", "c", "d").entries());
    ConfigureHeadersResponse(headerResponse, null, ImmutableList.of("c"), false);
  }

  @Override
  public void OnRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
    BuildBodyMutationResponse(bodyResponse, "body added", null, null);
  }

  @Override
  public void OnResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
    BuildBodyMutationResponse(bodyResponse, "body replaced", true, null);
  }

  public static void main(String[] args) throws IOException, InterruptedException {
    final ServiceCalloutExample server = new ServiceCalloutExample();
    server.start();
    server.blockUntilShutdown();
  }
}
