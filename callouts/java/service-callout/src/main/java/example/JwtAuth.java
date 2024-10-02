/*
 * Copyright 2024 Google LLC.
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

package example;

import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.SignatureException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import org.bouncycastle.openssl.PEMParser;
import org.bouncycastle.asn1.x509.SubjectPublicKeyInfo;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * Handles JWT authentication by extracting and validating JWT tokens from HTTP headers.
 * <p>
 * This class interacts with Envoy's external processing API to validate JWT tokens
 * and mutate HTTP headers based on the validation results.
 */
public class JwtAuth extends ServiceCallout {

    // Logger for the JwtAuth class
    private static final Logger logger = LoggerFactory.getLogger(JwtAuth.class);

    // RSA PublicKey used for JWT validation
    private final PublicKey publicKey;

    /**
     * Constructs a JwtAuth instance by loading the RSA public key from a PEM file.
     *
     * @param builder The builder instance containing configuration parameters.
     * @throws GeneralSecurityException If there is an issue generating the PublicKey.
     * @throws IOException If there is an issue reading the PEM file.
     */
    public JwtAuth(Builder builder) throws GeneralSecurityException, IOException {
        super(builder);
        this.publicKey = loadPublicKey("certs/publickey.pem");
    }

    /**
     * Builder specific to JwtAuth.
     * <p>
     * This builder follows the builder pattern, allowing for flexible and readable object creation.
     */
    public static class Builder extends ServiceCallout.Builder<Builder> {

        @Override
        public JwtAuth build() throws GeneralSecurityException, IOException {
            return new JwtAuth(this);
        }

        @Override
        protected Builder self() {
            return this;
        }
    }

    /**
     * Loads an RSA PublicKey from a PEM file located in the classpath.
     *
     * @param pemFilePath The path to the PEM file within the resources directory.
     * @return The loaded RSA PublicKey.
     * @throws IOException If there is an issue reading the PEM file.
     * @throws GeneralSecurityException If there is an issue generating the PublicKey.
     */
    public static PublicKey loadPublicKey(String pemFilePath) throws IOException, GeneralSecurityException {
        try (InputStream is = JwtAuth.class.getClassLoader().getResourceAsStream(pemFilePath)) {
            if (is == null) {
                throw new IOException("PEM file not found: " + pemFilePath);
            }

            try (PEMParser pemParser = new PEMParser(new InputStreamReader(is, StandardCharsets.UTF_8))) {
                Object object = pemParser.readObject();
                if (object instanceof SubjectPublicKeyInfo) {
                    SubjectPublicKeyInfo spki = (SubjectPublicKeyInfo) object;
                    byte[] encoded = spki.getEncoded();
                    X509EncodedKeySpec keySpec = new X509EncodedKeySpec(encoded);
                    KeyFactory keyFactory = KeyFactory.getInstance("RSA");
                    return keyFactory.generatePublic(keySpec);
                } else {
                    throw new IllegalArgumentException("Invalid PEM file: Not a valid SubjectPublicKeyInfo");
                }
            }
        }
    }

    /**
     * Extracts the JWT token from the 'Authorization' header.
     *
     * @param requestHeaders The HTTP headers received in the request.
     * @return The extracted JWT token if found and properly formatted, otherwise null.
     */
    public String extractJwtToken(HttpHeaders requestHeaders) {

        requestHeaders.getHeaders().getHeadersList().forEach(header -> {
            logger.info("Header: {} = {}", header.getKey(), header.getRawValue());
        });

        Optional<String> jwtToken = requestHeaders.getHeaders().getHeadersList().stream()
                .filter(header -> "Authorization".equalsIgnoreCase(header.getKey()))
                .map(header -> new String(header.getRawValue().toByteArray(), StandardCharsets.UTF_8))
                .findFirst()
                .map(authHeader -> {
                    String[] parts = authHeader.split(" ");
                    if (parts.length == 2 && "Bearer".equalsIgnoreCase(parts[0])) {
                        return parts[1];
                    } else {
                        logger.warn("Authorization header format is invalid.");
                        return null;
                    }
                });

        return jwtToken.orElse(null);
    }

    /**
     * Validates the JWT token using the loaded RSA public key.
     *
     * @param requestHeaders The HTTP headers from which to extract the JWT token.
     * @return The decoded JWT claims if valid, otherwise null.
     */
    public Claims validateJwtToken(HttpHeaders requestHeaders) {

        String jwtToken = extractJwtToken(requestHeaders);
        if (jwtToken == null) {
            logger.warn("JWT token is missing or invalid in the Authorization header.");
            return null;
        }

        try {
            // Decode the JWT token using the provided public key and algorithm
            Claims decoded = Jwts.parserBuilder()
                    .setSigningKey(publicKey)
                    .build()
                    .parseClaimsJws(jwtToken)
                    .getBody();

            logger.debug("JWT validated successfully: {}", decoded);
            return decoded;
        } catch (SignatureException e) {
            logger.error("Invalid JWT signature: {}", e.getMessage());
        } catch (io.jsonwebtoken.JwtException e) {
            logger.error("JWT processing error: {}", e.getMessage());
        }

        return null;
    }

    /**
     * Processes incoming request headers by validating the JWT token and mutating headers based on validation.
     *
     * @param processingResponseBuilder The builder for constructing the processing response.
     * @param headers                   The HTTP headers to process.
     */
    @Override
    public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {

        // Validate the JWT token
        Claims decoded = validateJwtToken(headers);

        if (decoded != null) {
            // Token is valid, add decoded items as header mutations
            Map<String, String> decodedItems = new HashMap<>();
            decoded.forEach((key, value) -> decodedItems.put("decoded-" + key, value.toString()));

            // Assuming addHeaderMutations adds the headers and returns a HeadersResponse
            ServiceCalloutTools.addHeaderMutations(
                    processingResponseBuilder.getRequestHeadersBuilder(),
                    decodedItems.entrySet(),  // Headers to add
                    null,                      // No headers to remove
                    true,                      // Clear route cache
                    null                       // No append action
            );
        } else {
            // Token is invalid, deny the request
            ServiceCalloutTools.denyCallout(
                    processingResponseBuilder.getResponseHeadersBuilder(),
                    "Authorization token is invalid"
            );
        }
    }

    /**
     * Main method to start the gRPC callout server with a custom configuration
     * using the {@link Builder}.
     * <p>
     * This method initializes the server with default or custom configurations,
     * starts the server, and keeps it running until manually terminated.
     * The server processes incoming gRPC requests for HTTP manipulations.
     * </p>
     *
     * <p>Usage:</p>
     * <pre>{@code
     * JwtAuth.Builder builder = new JwtAuth.Builder()
     *     .setIp("111.222.333.444")       // Customize IP
     *     .setPort(8443)                  // Set the port for secure communication
     *     .setEnableInsecurePort(true)    // Enable an insecure communication port
     *     .setServerThreadCount(4);       // Set the number of server threads
     * }</pre>
     *
     * @param args Command-line arguments, not used in this implementation.
     * @throws Exception If an error occurs during server startup or shutdown.
     */
    public static void main(String[] args) throws Exception {
        // Create a builder for JwtAuth with custom configuration
        JwtAuth server = new JwtAuth.Builder()
                .build();

        // Start the server and block until shutdown
        server.start();
        server.blockUntilShutdown();
    }
}