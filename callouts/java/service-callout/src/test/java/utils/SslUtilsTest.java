package utils;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import javax.net.ssl.SSLException;

import io.netty.handler.ssl.SslContext;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;

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
        final ByteArrayOutputStream outContent = new ByteArrayOutputStream();
        System.setErr(new PrintStream(outContent));

        SslUtils.readFileToBytes("non_existent_file.crt");
        assertTrue(outContent.toString().contains("File not found:"));

        System.setErr(System.err);
    }

    @Test
    public void testCreateSslContext() throws SSLException {
        byte[] certBytes = SslUtils.readFileToBytes("certs/server.crt");
        byte[] keyBytes = SslUtils.readFileToBytes("certs/pkcs8_key.pem");

        SslContext sslContext = SslUtils.createSslContext(certBytes, keyBytes);
        assertNotNull(sslContext);
    }

}
