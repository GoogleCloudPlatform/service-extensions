package utils;

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

import io.grpc.netty.GrpcSslContexts;
import io.netty.handler.ssl.SslContext;

import javax.net.ssl.SSLException;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * SslUtils provides utility methods for handling SSL contexts and reading SSL certificate and key files.
 */
public class SslUtils {
    private static final Logger logger = Logger.getLogger(SslUtils.class.getName());

    /**
     * Reads the content of a file into a byte array.
     * @param filePath The path of the file to be read
     * @return The byte array containing the file content, or null if an error occurs
     */
    public static byte[] readFileToBytes(String filePath)  {
        try (InputStream inputStream = SslUtils.class.getClassLoader().getResourceAsStream(filePath)) {
            if (inputStream == null) {
                throw new IOException("File not found: " + filePath);
            }
            return inputStream.readAllBytes();
        } catch (IOException e) {
            logger.log(Level.WARNING, "readAllBytes error:", e);
            return null;
        }
    }

    /**
     * Creates an SSL context from certificate and key byte arrays.
     * @param certBytes The byte array containing the certificate content
     * @param keyBytes The byte array containing the key content
     * @return The SSL context created from the certificate and key, or null if an SSLException occurs
     * @throws SSLException If an SSL error occurs while creating the SSL context
     */
    public static SslContext createSslContext(byte[] certBytes, byte[] keyBytes) throws SSLException {
        return GrpcSslContexts.forServer(new ByteArrayInputStream(certBytes), new ByteArrayInputStream(keyBytes))
                .build();
    }
}
