package iq.ready.billpay.demo;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Exact-origin policy shared by the native settings and WebView callbacks. */
public final class EndpointPolicy {
    public static final String DEFAULT_ENDPOINT = "http://127.0.0.1:8765/";

    private EndpointPolicy() {}

    public static String normalize(String input) {
        if (input == null || input.length() > 2048) throw invalid();
        String value = input.trim();
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (scheme == null || host == null || host.isEmpty()) throw invalid();
            scheme = scheme.toLowerCase(Locale.ROOT);
            host = host.toLowerCase(Locale.ROOT);
            if (uri.getRawUserInfo() != null || uri.getRawQuery() != null
                    || uri.getRawFragment() != null || uri.isOpaque()) throw invalid();
            if (uri.getRawPath() != null && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath())) throw invalid();
            int port = uri.getPort();
            if (port != -1 && (port < 1 || port > 65535)) throw invalid();
            boolean local = "127.0.0.1".equals(host) || "localhost".equals(host);
            if (!"https".equals(scheme) && !("http".equals(scheme) && local)) throw invalid();
            // An explicit empty port is not an endpoint, even if URI maps it to -1.
            if (uri.getRawAuthority().endsWith(":")) throw invalid();
            if (("https".equals(scheme) && port == 443)
                    || ("http".equals(scheme) && port == 80)) port = -1;
            return new URI(scheme, null, host, port, "/", null, null).toASCIIString();
        } catch (URISyntaxException error) {
            throw invalid();
        }
    }

    public static boolean isSameOrigin(String endpoint, String candidate) {
        if (candidate == null || candidate.length() > 8192) return false;
        try {
            URI allowed = new URI(normalize(endpoint));
            URI target = new URI(candidate);
            if (target.getHost() == null || target.getScheme() == null
                    || target.getRawUserInfo() != null || target.isOpaque()) return false;
            return allowed.getScheme().equalsIgnoreCase(target.getScheme())
                    && allowed.getHost().equalsIgnoreCase(target.getHost())
                    && effectivePort(allowed) == effectivePort(target);
        } catch (IllegalArgumentException | URISyntaxException error) {
            return false;
        }
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() != -1) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("Use http://127.0.0.1:8765 or an HTTPS origin, without a path, credentials, query, or fragment.");
    }
}
