package example;

/*
 * Copyright 2024 The gRPC Authors
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


import io.envoyproxy.envoy.service.ext_proc.v3.BodyResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpBody;
import service.ServiceCallout;

import java.io.IOException;

import static service.ServiceCalloutTools.AddBodyMutations;

/**
 *  Example callout server.
 *
 *  Provides a non-comprehensive set of responses for each of the possible
 *  callout interactions.
 *
 *  On a request body callout we provide a mutation to append '-added-body' to the body. On response body
 *  callouts we send a mutation to replace the body with 'new-body'.
 */

public class AddBody extends ServiceCallout {

    @Override
    public void OnRequestBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        AddBodyMutations(bodyResponse, "body added", null, null);
    }

    @Override
    public void OnResponseBody(BodyResponse.Builder bodyResponse, HttpBody body) {
        AddBodyMutations(bodyResponse, "body replaced", true, null);
    }

    public static void main(String[] args) throws IOException, InterruptedException {
        final ServiceCallout server = new AddBody();
        server.start();
        server.blockUntilShutdown();
    }

}
