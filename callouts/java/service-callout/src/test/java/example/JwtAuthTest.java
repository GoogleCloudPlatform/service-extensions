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
import com.google.common.truth.Truth;
import com.google.protobuf.ByteString;
import io.envoyproxy.envoy.config.core.v3.HeaderMap;
import io.envoyproxy.envoy.config.core.v3.HeaderValue;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.Mockito;
import service.ServiceCallout;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.HashMap;
import java.util.Map;

import static org.junit.Assert.assertThrows;

public class JwtAuthTest {

    private JwtAuth server;

    @Before
    public void setUp() throws GeneralSecurityException, IOException {
        server = Mockito.spy(new JwtAuth.Builder()
                .build());
    }

    @After
    public void tearDown() throws Exception {
        stopServer();
    }

    public static String generateTestJWTToken(RSAPrivateKey privateKey, Map<String, Object> claims) throws Exception {
        Algorithm algorithm = Algorithm.RSA256(null, privateKey);
        return JWT.create().withPayload(claims).sign(algorithm);
    }

    // Helper method to load a private key from a file
    private RSAPrivateKey loadPrivateKey(String keyFilePath) throws Exception {
        File file = new File(keyFilePath);
        byte[] keyBytes = new byte[(int) file.length()];
        try (FileInputStream fis = new FileInputStream(file)) {
            fis.read(keyBytes);
        }

        String privateKeyPEM = new String(keyBytes)
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replaceAll("\\s+", "");

        byte[] decoded = java.util.Base64.getDecoder().decode(privateKeyPEM);
        PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(decoded);
        KeyFactory keyFactory = KeyFactory.getInstance("RSA");
        return (RSAPrivateKey) keyFactory.generatePrivate(spec);
    }

    @Test
    public void testHandleRequestHeaders_ValidToken() throws Exception {
        // Load the private key
        RSAPrivateKey privateKey = loadPrivateKey("src/main/resources/certs/localhost_private.pem");

        // Create claims for the JWT
        Map<String, Object> claims = new HashMap<>();
        claims.put("sub", "1234567890");
        claims.put("name", "John Doe");
        claims.put("iat", 1720020355L);
        claims.put("exp", 1820023955L);

        // Generate the JWT token
        String tokenString = generateTestJWTToken(privateKey, claims);

        // Create the HeaderMap with Authorization header
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder()
                        .setKey("Authorization")
                        .setRawValue(ByteString.copyFrom(("Bearer " + tokenString).getBytes(StandardCharsets.UTF_8)))
                        .build())
                .build();


        HttpHeaders requestHeaders = HttpHeaders.newBuilder().setHeaders(headerMap).build();

        ProcessingResponse.Builder responseBuilder = ProcessingResponse.newBuilder();

        server.onRequestHeaders(responseBuilder, requestHeaders);

        ProcessingResponse response = responseBuilder.build();

        Truth.assertThat(response).isNotNull();

        Truth.assertThat(requestHeaders.getHeaders().getHeadersList().stream()
                .anyMatch(h -> h.getKey().equals("decode-sub") && new String(String.valueOf(h.getRawValue())).equals("1234567890")));

        Truth.assertThat(requestHeaders.getHeaders().getHeadersList().stream()
                .anyMatch(h -> h.getKey().equals("decoded-name") && new String(String.valueOf(h.getRawValue())).equals("John Doe")));
    }

    @Test
    public void testHandleRequestHeaders_InvalidToken() throws Exception {
        // Create the HeaderMap with an invalid token
        HeaderMap headerMap = HeaderMap.newBuilder()
                .addHeaders(HeaderValue.newBuilder()
                        .setKey("Authorization")
                        .setRawValue(ByteString.copyFrom("Bearer invalidtoken".getBytes(StandardCharsets.UTF_8)))
                        .build())
                .build();

        HttpHeaders requestHeaders = HttpHeaders.newBuilder().setHeaders(headerMap).build();

        // Prepare a response builder
        ProcessingResponse.Builder responseBuilder = ProcessingResponse.newBuilder();

        // Call the service method
        StatusRuntimeException exception = assertThrows(StatusRuntimeException.class, () -> {
            server.onRequestHeaders(responseBuilder, requestHeaders);
        });

        // Assert the error code and message
        Truth.assertThat(exception.getStatus().getCode())
                .isEqualTo(Status.PERMISSION_DENIED.getCode());
        Truth.assertThat("Authorization token is invalid")
                .isEqualTo(exception.getStatus().getDescription());
    }

    private void stopServer() throws Exception {
        Method stopMethod = ServiceCallout.class.getDeclaredMethod("stop");
        stopMethod.setAccessible(true);
        stopMethod.invoke(server);
    }
}