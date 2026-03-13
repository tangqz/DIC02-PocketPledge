## 2025-03-11 - Sensitive Token Logging in WebSocket Authentication
**Vulnerability:** The HTTP middleware logged all incoming request query parameters directly to the system logs. Since the application uses query parameters for WebSocket authentication (e.g., `/ws?token=JWT_TOKEN`), the raw JWT access tokens were being leaked in plaintext logs.
**Learning:** While the body of incoming requests was properly sanitized through a mask function (`_mask_sensitive`), the URL query string was omitted from this security measure, exposing an alternative vector for credential leaks.
**Prevention:** Introduce a query parameter sanitization step (e.g., using `urllib.parse.parse_qsl` and `urllib.parse.urlencode`) to safely redact known sensitive keys from `request.url.query` before passing them to the logging module.
## 2024-06-03 - [Timing Attack in Tool Token Verification]
**Vulnerability:** The internal tool token was verified using a direct string comparison (`!=`), which is vulnerable to timing attacks. This could allow an attacker to guess the token by measuring the time it takes to compare characters.
**Learning:** String comparisons for sensitive tokens or passwords should always use constant-time operations to prevent timing leaks.
**Prevention:** Use `hmac.compare_digest` for all string comparisons involving secrets.
