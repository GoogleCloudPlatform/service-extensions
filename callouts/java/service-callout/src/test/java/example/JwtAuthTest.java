/*
 * Copyright (c) 2024 Google, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package example;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderMap;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.service.ext_proc.v3.ExternalProcessorGrpc;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.security.interfaces.RSAPrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.KeyFactory;
import java.util.Base64;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

public class JwtAuthTest {

    @Test
    public void testJwtAuthRS256Failure() {
        ManagedChannel channel = ManagedChannelBuilder.forAddress("localhost", 8080)
                .usePlaintext()
                .build();

        ExternalProcessorGrpc.ExternalProcessorBlockingStub stub = ExternalProcessorGrpc.newBlockingStub(channel);

        // Construct HeaderMap
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder().setKey("Authorization").setRawValue(ByteString.fromHex("")).build())
                .build();

        // Construct HttpHeaders
        HttpHeaders requestHeaders = HttpHeaders.newBuilder()
                .setHeaders(headerMap)
                .setEndOfStream(true)
                .build();

        // Expect a PERMISSION_DENIED exception
        assertThrows(StatusRuntimeException.class, () -> {
            makeRequest(stub, requestHeaders);
        }, "Expected PERMISSION_DENIED status");

        // Shutdown the channel
        channel.shutdown();
    }

    @Test
    public void testJwtAuthRS256Success() throws Exception {
        ManagedChannel channel = ManagedChannelBuilder.forAddress("localhost", 8080)
                .usePlaintext()
                .build();

        ExternalProcessorGrpc.ExternalProcessorBlockingStub stub = ExternalProcessorGrpc.newBlockingStub(channel);

        // Load the private key
        RSAPrivateKey privateKey = loadPrivateKey("./extproc/ssl_creds/privatekey.pem");

        // Define JWT payload
        Map<String, Object> payload = new HashMap<>();
        payload.put("sub", "1234567890");
        payload.put("name", "John Doe");
        payload.put("admin", true);
        payload.put("iat", new Date().getTime() / 1000); // Issue time (in seconds)
        payload.put("exp", (new Date().getTime() / 1000) + 3600); // Expiry in one hour

        // Generate the JWT token
        String jwtToken = JWT.create()
                .withPayload(payload)
                .sign(Algorithm.RSA256(null, privateKey));

        // Construct Authorization header value
        String authorizationHeaderValue = "Bearer " + jwtToken;

        // Construct HeaderMap
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder().setKey("Authorization")
                        .setRawValue(ByteString.copyFrom(authorizationHeaderValue.getBytes(StandardCharsets.UTF_8)))
                        .build())
                .build();

        // Construct HttpHeaders
        HttpHeaders requestHeaders = HttpHeaders.newBuilder()
                .setHeaders(headerMap)
                .setEndOfStream(true)
                .build();

        // Send request and get the response
        HttpHeaders response = makeRequest(stub, requestHeaders);

        // Validate response
        assertNotNull(response, "Response should not be null");
        assertTrue(response.hasHeaders(), "Response should contain request headers");

        // Shutdown the channel
        channel.shutdown();
    }

    // Helper function to make the gRPC request
    private HttpHeaders makeRequest(ExternalProcessorGrpc.ExternalProcessorBlockingStub stub, HttpHeaders requestHeaders) {
        return // Chamada JWT
    }

    // Helper function to load private key from a PEM file
    private RSAPrivateKey loadPrivateKey(String privateKeyPath) throws Exception {
        File file = new File(privateKeyPath);
        byte[] keyBytes = new byte[(int) file.length()];
        try (FileInputStream fis = new FileInputStream(file)) {
            fis.read(keyBytes);
        }

        String privateKeyPEM = new String(keyBytes)
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replaceAll("\\s+", "");

        byte[] decoded = Base64.getDecoder().decode(privateKeyPEM);
        PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(decoded);
        KeyFactory keyFactory = KeyFactory.getInstance("RSA");
        return (RSAPrivateKey) keyFactory.generatePrivate(spec);
    }
}
