package utils;

import io.grpc.netty.GrpcSslContexts;
import io.netty.handler.ssl.SslContext;

import javax.net.ssl.SSLException;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.logging.Level;
import java.util.logging.Logger;

public class SslUtils {
    private static final Logger logger = Logger.getLogger(SslUtils.class.getName());

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

    public static SslContext createSslContext(byte[] certBytes, byte[] keyBytes) throws SSLException {
        return GrpcSslContexts.forServer(new ByteArrayInputStream(certBytes), new ByteArrayInputStream(keyBytes))
                .build();
    }
}
