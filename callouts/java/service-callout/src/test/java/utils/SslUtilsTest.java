package utils;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNull;

import javax.net.ssl.SSLException;

import io.netty.handler.ssl.SslContext;

import org.junit.Test;

public class SslUtilsTest {

    @Test
    public void testReadFileToBytes() {
        byte[] bytes = SslUtils.readFileToBytes("certs/server.crt");
        assertNotNull(bytes);
        assertTrue(bytes.length > 0);
    }

    @Test
    public void testReadFileToBytesNonExistentFile() {
        byte[] bytes = SslUtils.readFileToBytes("non_existent_file.crt");
        assertNull(bytes, "Expected null when file does not exist");
    }

    @Test
    public void testCreateSslContext() throws SSLException {
        byte[] certBytes = SslUtils.readFileToBytes("certs/server.crt");
        byte[] keyBytes = SslUtils.readFileToBytes("certs/pkcs8_key.pem");

        SslContext sslContext = SslUtils.createSslContext(certBytes, keyBytes);
        assertNotNull(sslContext);
    }

}
