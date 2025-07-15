import aiohttp, rsa, base64, json, struct, hmac, hashlib, time
from pathlib import Path
from typing import Dict, Optional

_CHARS = "23456789BCDFGHJKMNPQRTVWXY"
_STEAM_BASES = (
    "https://store.steampowered.com",
    "https://steamcommunity.com",
)


def _totp(shared_secret: str, ts: int) -> str:
    key = base64.b64decode(shared_secret)
    msg = struct.pack(">Q", ts // 30)
    dig = hmac.new(key, msg, hashlib.sha1).digest()
    off = dig[-1] & 0x0F
    code_int = struct.unpack(">I", dig[off : off + 4])[0] & 0x7FFFFFFF
    out = []
    for _ in range(5):
        code_int, idx = divmod(code_int, len(_CHARS))
        out.append(_CHARS[idx])
    return "".join(out)


class SteamClient:
    def __init__(
        self,
        username: str,
        password: str,
        mafile: str | Path,
        *,
        proxy: str | None = None,       # "http://user:pass@ip:port"  или  "socks5://..."
        debug: bool = False,
    ):
        self.username, self.password = username, password
        self.guard = json.loads(Path(mafile).read_text("utf-8"))
        self.debug = debug

        # ── connector / proxy ───────────────────────
        connector = None
        self.proxy = self.proxy_auth = None
        if proxy:
            if proxy.startswith("socks"):
                from aiohttp_socks import ProxyConnector

                connector = ProxyConnector.from_url(proxy)
            else:  # http/https
                self.proxy = proxy
                if "@" in proxy:                         # авторизация в url
                    cred, _ = proxy.split("@", 1)
                    user, pwd = cred.split("//")[1].split(":")
                    self.proxy_auth = aiohttp.BasicAuth(user, pwd)

        # ── сессия ──────────────────────────────────
        self.sess = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.CookieJar(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    # ── helpers ─────────────────────────────────────
    async def _json_post(self, url: str, **kw) -> Dict:
        async with self.sess.post(url, proxy=self.proxy, proxy_auth=self.proxy_auth, **kw) as r:
            txt = await r.text()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            if self.debug:
                print(f"[Steam DEBUG] {url}\nstatus={r.status}\nraw[:400]=\n{txt[:400]}\n")
            return {}

    # ── public ──────────────────────────────────────
    async def login(self) -> Dict[str, str]:
        # warm‑up
        await self.sess.get(
            "https://steamcommunity.com/login/",
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

        for base in _STEAM_BASES:
            rsa_info = await self._json_post(f"{base}/login/getrsakey/", data={"username": self.username})
            if not rsa_info.get("success"):
                continue

            mod = int(rsa_info["publickey_mod"], 16)
            exp = int(rsa_info["publickey_exp"], 16)
            ts  = rsa_info["timestamp"]
            enc_pwd = base64.b64encode(
                rsa.encrypt(self.password.encode(), rsa.PublicKey(mod, exp))
            ).decode()

            res = await self._json_post(
                f"{base}/login/dologin/",
                data={
                    "username": self.username,
                    "password": enc_pwd,
                    "twofactorcode": "",
                    "rsatimestamp": ts,
                    "remember_login": "false",
                },
            )

            if res.get("requires_twofactor"):
                now = int(time.time())
                for d in (0, -30, 30):
                    code = _totp(self.guard["shared_secret"], now + d)
                    res = await self._json_post(
                        f"{base}/login/dologin/",
                        data={
                            "username": self.username,
                            "password": enc_pwd,
                            "twofactorcode": code,
                            "rsatimestamp": ts,
                            "remember_login": "false",
                        },
                    )
                    if res.get("success"):
                        break

            if res.get("success"):
                return {
                    c.key: c.value
                    for c in self.sess.cookie_jar
                    if c.key in {"steamLoginSecure", "sessionid"}
                }

        raise RuntimeError("Steam login failed")

    async def close(self): await self.sess.close()
