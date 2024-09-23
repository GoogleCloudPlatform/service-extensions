package example;// Copyright 2024 Google LLC.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import io.envoyproxy.envoy.service.ext_proc.v3.HeadersResponse;
import io.envoyproxy.envoy.service.ext_proc.v3.HttpHeaders;
import io.envoyproxy.envoy.service.ext_proc.v3.ProcessingResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import service.ServiceCalloutTools;

import java.security.Key;
import java.security.SignatureException;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class JwtAuth {

    public class JwtTokenExtractor {

        public JwtAuth(byte[] publicKey) {
            this.publicKey = publicKey;
        }
        private static final Logger logger = LoggerFactory.getLogger(JwtTokenValidator.class);
        private byte[] publicKey;


        public static String extractJwtToken(HttpHeaders requestHeaders) {
            /*
             * Extracts the JWT token from the request headers, specifically looking for
             * the 'Authorization' header and parsing out the token part.
             *
             * Args:
             *     requestHeaders (HttpHeaders): The HTTP headers received in the request.
             *
             * Returns:
             *     String: The extracted JWT token if found, otherwise null.
             *
             * Example:
             *     Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6...
             *     -> Returns: eyJhbGciOiJIUzI1NiIsInR5cCI6...
             */

            Optional<String> jwtToken = requestHeaders.getHeaders().stream()
                    .filter(header -> header.getKey().equalsIgnoreCase("Authorization"))
                    .map(header -> new String(header.getRawValue()))
                    .findFirst();

            if (jwtToken.isPresent() && jwtToken.get().contains(" ")) {
                return jwtToken.get().split(" ")[1];
            }

            return jwtToken.orElse(null);
        }

        // Method to validate JWT token
        public static Claims validateJwtToken(byte[] key, HttpHeaders requestHeaders, String algorithm) {
            /*
             * Validates the JWT token extracted from the request headers using a specified
             * public key and algorithm. If valid, returns the decoded JWT payload; otherwise,
             * logs an error and returns null.
             *
             * Args:
             *     key (byte[]): The public key used for token validation.
             *     requestHeaders (HttpHeaders): The HTTP headers received in the request,
             *                                   used to extract the JWT token.
             *     algorithm (String): The algorithm with which the JWT was signed (e.g., 'RS256').
             *
             * Returns:
             *     Claims: The decoded JWT if validation is successful, null if the token is
             *             invalid or an error occurs.
             */

            String jwtToken = JwtTokenExtractor.extractJwtToken(requestHeaders);
            if (jwtToken == null) {
                logger.warn("Token failed to decode.");
                return null;
            }

            try {
                Key publicKey = Keys.hmacShaKeyFor(key);

                // Decode the JWT token using the provided key and algorithm
                Claims decoded = Jwts.parserBuilder()
                        .setSigningKey(publicKey)
                        .build()
                        .parseClaimsJws(jwtToken)
                        .getBody();

                logger.info("Approved - Decoded Values: {}", decoded);
                return decoded;
            } catch (SignatureException e) {
                logger.error("Invalid Token Signature: {}", e.getMessage());
                return null;
            } catch (Exception e) {
                logger.error("Error validating token: {}", e.getMessage());
                return null;
            }
        }

        public HeadersResponse onRequestHeaders(ProcessingResponse.Builder processingResponseBuilder, HttpHeaders headers) {
            /*
             * Deny token if validation fails and return an error message.
             *
             * If the token is valid, apply a header mutation.
             */

            // Validate the JWT token
            Claims decoded = validateJwtToken(publicKey, headers, "RS256");

            if (decoded != null) {
                // Token is valid, add decoded items as header mutations
                Map<String, String> decodedItems = new HashMap<>();
                decoded.forEach((key, value) -> decodedItems.put("decoded-" + key, value.toString()));

                // Assuming addHeaderMutation adds the headers and returns a HeadersResponse
                return ServiceCalloutTools.addHeaderMutations(decodedItems, true, null, true, null);
            } else {
                // Token is invalid, deny the request
                ServiceCalloutTools.denyCallout(processingResponseBuilder.getResponseHeadersBuilder(),
                        "Authorization token is invalid");
                return null;
            }
        }

    }
}