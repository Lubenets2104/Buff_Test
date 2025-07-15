import base64, hmac, struct, hashlib, time

def steam_guard_code(shared_secret):
    t = int(time.time()) // 30
    secret = base64.b64decode(shared_secret)
    time_bytes = struct.pack(">Q", t)
    hmac_digest = hmac.new(secret, time_bytes, hashlib.sha1).digest()
    start = hmac_digest[19] & 0x0F
    fullcode = struct.unpack(">I", hmac_digest[start:start + 4])[0] & 0x7fffffff
    chars = "23456789BCDFGHJKMNPQRTVWXY"
    code = ""
    for _ in range(5):
        code += chars[fullcode % len(chars)]
        fullcode //= len(chars)
    return code

print(steam_guard_code("6HhNkcOw8AouccF8yT3zonGiclg="))  # ← подставь свой shared_secret из maFile
