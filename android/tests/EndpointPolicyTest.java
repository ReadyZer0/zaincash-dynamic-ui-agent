package iq.ready.billpay.demo;

public final class EndpointPolicyTest {
    private static int checks = 0;
    private static void check(boolean condition, String label) {
        checks++;
        if (!condition) throw new AssertionError(label);
    }
    private static void reject(String url) {
        boolean rejected = false;
        try { EndpointPolicy.normalize(url); }
        catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, "must reject " + url);
    }
    public static void main(String[] args) {
        check(EndpointPolicy.DEFAULT_ENDPOINT.equals(EndpointPolicy.normalize("http://127.0.0.1:8765")), "local normalization");
        check("http://localhost:8765/".equals(EndpointPolicy.normalize("http://LOCALHOST:8765/")), "localhost normalization");
        check("https://demo.example/".equals(EndpointPolicy.normalize("https://DEMO.example:443/")), "https normalization");
        for (String url : new String[]{null, "", "file:///tmp/test", "javascript:alert(1)", "content://test", "http://192.168.1.5:8765", "http://127.0.0.1.evil.example", "http://localhost.evil.example", "https://name:secret@demo.example", "https://demo.example/path", "https://demo.example/?key=secret", "https://demo.example/#token", "https://demo.example:0", "https://demo.example:65536", "https://demo.example:", "https://demo.example\\@evil.example", "https:///demo.example", "http://2130706433", "http://127.1", "https://demo.example/%2f"}) reject(url);
        String base = "http://127.0.0.1:8765/";
        check(EndpointPolicy.isSameOrigin(base, base + "api/chat"), "api permitted");
        check(EndpointPolicy.isSameOrigin(base, base + "api/bootstrap?user_id=demo_amina"), "query permitted for API");
        for (String url : new String[]{"https://127.0.0.1:8765/", "http://127.0.0.1:8766/", "http://127.0.0.1:8765.evil.example/", "http://127.0.0.1.evil.example:8765/", "http://127.0.0.1:8765@evil.example/", "http://evil.example@127.0.0.1:8765/", "http://localhost:8765/", "javascript:alert(1)", "file:///tmp/app.js", "content://local/app.js", "//127.0.0.1:8765/", null}) check(!EndpointPolicy.isSameOrigin(base, url), "foreign origin blocked: " + url);
        check(EndpointPolicy.isSameOrigin("https://demo.example/", "https://demo.example:443/api/chat"), "default HTTPS port");
        System.out.println("Endpoint policy: " + checks + " checks passed");
    }
}
