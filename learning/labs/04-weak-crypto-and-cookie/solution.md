# Lab 04 solution

1. Restore the HMAC in `_sign`:
   `hmac.new(secret.encode("utf-8"), body.encode("ascii"), sha256).digest()`.
   HMAC is the correct construction for authenticating a message with a secret
   key; `hash(secret + message)` is not, whichever hash you pick.
2. Restore `httponly=True` on the session cookie. Keep `secure=settings.https_only`
   as it is: the existing comment explains why it cannot be hardcoded.
3. The existing session tests in `server/test/` should fail against the MD5
   version only if they pin token bytes; if they pass, note that tests verified
   *behaviour*, not *security*, which is why a separate scanner stage exists.
