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
import io.jsonwebtoken.JwtParser;
import io.jsonwebtoken.Jwts;
import org.bouncycastle.asn1.x509.SubjectPublicKeyInfo;
import org.bouncycastle.openssl.PEMParser;
import org.conscrypt.Conscrypt;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import service.ServiceCallout;
import service.ServiceCalloutTools;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.Security;
import java.security.spec.X509EncodedKeySpec;
import java.util.HashMap;
import java.util.Map;

/**
 * JWT authentication handler with Google Conscrypt acceleration.
 * <p>
 * This variant uses:
 * - Conscrypt for native BoringSSL-backed crypto operations
 * - Cached JwtParser instance (thread-safe, reusable)
 */
public class JwtAuth extends ServiceCallout {

    private static final Logger logger = LoggerFactory.getLogger(JwtAuth.class);

    // RSA PublicKey used for JWT validation
    private final PublicKey publicKey;

    private final JwtParser jwtParser;

    static {
        try {
            // Install Conscrypt as the highest priority security provider
            // This makes crypto operations use native BoringSSL instead of Java crypto
            Security.insertProviderAt(Conscrypt.newProvider(), 1);

            // Verify Conscrypt is working correctly
            String rsaProvider = Security.getProviders("Signature.SHA256withRSA")[0].getName();
            logger.info("Conscrypt installed successfully. RSA provider: {}", rsaProvider);
        } catch (Exception e) {
            logger.warn("Failed to install Conscrypt, falling back to default provider: {}", e.getMessage());
        }
    }

    /**
     * Constructs a JwtAuth instance with Conscrypt-accelerated crypto.
     *
     * @param builder The builder instance containing configuration parameters.
     * @throws GeneralSecurityException If there is an issue generating the PublicKey.
     * @throws IOException              If there is an issue reading the PEM file.
     */
    public JwtAuth(Builder builder) throws GeneralSecurityException, IOException {
        super(builder);
        this.publicKey = loadPublicKey("certs/publickey.pem");

        // Pre-build the parser once
        // NOTE: If key rotation is needed, this pattern must be changed to rebuild
        // the parser when keys change (e.g., using JWKS with periodic refresh).
        this.jwtParser = Jwts.parserBuilder()
                .setSigningKey(publicKey)
                .build();

        logger.info("JwtAuth initialized with cached JwtParser");
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
     * @throws IOException              If there is an issue reading the PEM file.
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
        var headersList = requestHeaders.getHeaders().getHeadersList();
        for (var header : headersList) {
            if ("Authorization".equalsIgnoreCase(header.getKey())) {
                String authHeader;
                byte[] rawValue = header.getRawValue().toByteArray();
                if (rawValue != null && rawValue.length > 0) {
                    authHeader = new String(rawValue, StandardCharsets.UTF_8);
                } else {
                    authHeader = header.getValue();
                }

                int spaceIdx = authHeader.indexOf(' ');
                if (spaceIdx > 0 && spaceIdx < authHeader.length() - 1) {
                    String scheme = authHeader.substring(0, spaceIdx);
                    if ("Bearer".equalsIgnoreCase(scheme)) {
                        return authHeader.substring(spaceIdx + 1);
                    }
                }
                return null;
            }
        }
        return null;
    }

    /**
     * Validates JWT token synchronously - called from executor thread.
     * Uses Conscrypt-accelerated RSA verification.
     *
     * @param jwtToken The JWT token string to validate.
     * @return The decoded JWT claims if valid, otherwise null.
     */
    private Claims validateJwtTokenSync(String jwtToken) {
        try {
            return jwtParser.parseClaimsJws(jwtToken).getBody();
        } catch (io.jsonwebtoken.JwtException e) {
            return null;
        }
    }

    /**
     * Processes incoming request headers by validating the JWT token and mutating headers based on validation.
     * Note: Currently synchronous due to gRPC servicer interface constraints.
     * The Conscrypt provider still accelerates the crypto operations.
     *
     * @param processingResponseBuilder The builder for constructing the processing response.
     * @param headers                   The HTTP headers to process.
     */
    @Override
    public void onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {
        // Extract token
        String jwtToken = extractJwtToken(headers);
        if (jwtToken == null) {
            ServiceCalloutTools.denyCallout(
                    processingResponseBuilder.getResponseHeadersBuilder(),
                    "No Authorization token found"
            );
            return;
        }

        // Validate the JWT token
        Claims decoded = validateJwtTokenSync(jwtToken);

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
     *     .setSecurePort(8443)            // Set the port for secure communication
     *     .setEnablePlainTextPort(true)   // Enable an plaintext communication port
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
