## 2025-03-11 - Sensitive Token Logging in WebSocket Authentication
**Vulnerability:** The HTTP middleware logged all incoming request query parameters directly to the system logs. Since the application uses query parameters for WebSocket authentication (e.g., `/ws?token=JWT_TOKEN`), the raw JWT access tokens were being leaked in plaintext logs.
**Learning:** While the body of incoming requests was properly sanitized through a mask function (`_mask_sensitive`), the URL query string was omitted from this security measure, exposing an alternative vector for credential leaks.
**Prevention:** Introduce a query parameter sanitization step (e.g., using `urllib.parse.parse_qsl` and `urllib.parse.urlencode`) to safely redact known sensitive keys from `request.url.query` before passing them to the logging module.
## 2024-06-03 - [Timing Attack in Tool Token Verification]
**Vulnerability:** The internal tool token was verified using a direct string comparison (`!=`), which is vulnerable to timing attacks. This could allow an attacker to guess the token by measuring the time it takes to compare characters.
**Learning:** String comparisons for sensitive tokens or passwords should always use constant-time operations to prevent timing leaks.
**Prevention:** Use `hmac.compare_digest` for all string comparisons involving secrets.
## 2024-03-14 - Prevent Deadlocks when updating multiple Wallet balances
**Vulnerability:** A race condition existed where concurrent requests could perform conflicting modifications to wallet balances because they were fetched without row-level database locks. Furthermore, fetching multiple locks without consistent ordering could lead to deadlocks (e.g., Session A locks Wallet 1 then Wallet 2; Session B locks Wallet 2 then Wallet 1).
**Learning:** In a financial system or any environment involving shared numerical balances modified by multiple sources simultaneously, pessimistic locking (e.g., `SELECT ... FOR UPDATE` via SQLAlchemy's `with_for_update()`) is strictly necessary. Multiple locks MUST be acquired in a deterministic order (like ascending primary key IDs) to prevent deadlock states across concurrent transactions.
**Prevention:** Implement a helper like `_require_wallet_for_update(db, user_id)` and manually ensure that in methods updating multiple accounts (like `execute_penalty`), the calls always retrieve locks starting from ID 0 upwards (System IDs `0`, `1`, then the User ID `user_id > 1`).

## 2024-03-21 - [CRITICAL] Prevent User Enumeration Timing Attack
**Vulnerability:** The login endpoint returns a 401 error early if a user is not found, skipping the costly `pbkdf2` password hash verification. This timing difference allows attackers to enumerate valid usernames.
**Learning:** This existed because fast-failing is a standard development practice, but it leaked whether a user existed via timing differences.
**Prevention:** Pre-computed a DUMMY_HASH using the exact same PBKDF2 parameters as standard passwords. When a user is not found, perform a dummy verification with this hash before returning the 401 error.
