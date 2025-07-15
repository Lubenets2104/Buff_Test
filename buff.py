import aiohttp
from typing import Dict, Any
import re
from urllib.parse import urlparse, parse_qs, unquote

BUFF = "https://buff.163.com"
FORM_URL = BUFF + "/account/login/steam?back_url=/"
STEAM_POST = "https://steamcommunity.com/openid/login"
HEAD_API = {"X-Requested-With": "XMLHttpRequest"}


class BuffClient:
    def __init__(self, steam, *, debug=False):
        self.steam = steam
        self.sess = steam.sess
        self.proxy, self.proxy_auth = steam.proxy, steam.proxy_auth
        self.debug = debug

    async def login(self) -> Dict[str, str]:
        if self.debug:
            print("\n[BUFF] Начинаем авторизацию")

        # 1. Получаем OpenID параметры от Buff
        async with self.sess.get(
                FORM_URL,
                proxy=self.proxy,
                proxy_auth=self.proxy_auth,
                allow_redirects=False
        ) as resp:
            if self.debug:
                print(f"[BUFF] Buff login page → {resp.status}")

            if resp.status == 302:
                steam_url = resp.headers.get('Location')
                if self.debug:
                    print(f"[BUFF] Редирект на: {steam_url[:100]}...")

                parsed = urlparse(steam_url)
                query_params = parse_qs(parsed.query)

                goto = query_params.get('goto', [''])[0]
                if goto:
                    goto_decoded = unquote(goto)
                    if '?' in goto_decoded:
                        nested_params = parse_qs(goto_decoded.split('?', 1)[1])

                        openid_data = {}
                        for key, values in nested_params.items():
                            openid_data[key] = values[0] if values else ''

                        if self.debug:
                            print(f"[BUFF] OpenID параметры извлечены: {len(openid_data)} полей")

                        return await self._submit_openid(openid_data)

            elif resp.status == 200:
                text = await resp.text()
                if 'loginCallback' not in text and 'login-btn' not in text:
                    cookies = self._get_cookies()
                    if cookies:
                        if self.debug:
                            print("[BUFF] Уже авторизованы")
                        return cookies

        raise RuntimeError("Не удалось начать OpenID процесс")

    async def _submit_openid(self, openid_params: Dict[str, str]) -> Dict[str, str]:
        if self.debug:
            print("[BUFF] Отправляем OpenID запрос напрямую")

        async with self.sess.post(
                STEAM_POST,
                data=openid_params,
                proxy=self.proxy,
                proxy_auth=self.proxy_auth,
                allow_redirects=False,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': 'https://steamcommunity.com/'
                }
        ) as resp:
            if self.debug:
                print(f"[BUFF] Steam OpenID POST → {resp.status}")

            if resp.status in (302, 303):
                location = resp.headers.get('Location')

                if location and 'buff.163.com' in location:
                    if self.debug:
                        print("[BUFF] Steam авторизовал, возвращаемся на Buff")

                    async with self.sess.get(
                            location,
                            proxy=self.proxy,
                            proxy_auth=self.proxy_auth,
                            allow_redirects=True
                    ) as buff_resp:
                        if self.debug:
                            print(f"[BUFF] Buff callback → {buff_resp.status}")
                            final_url = str(buff_resp.url)
                            print(f"[BUFF] Final URL: {final_url}")

                        if 'steamcommunity.com' in str(buff_resp.url):
                            html = await buff_resp.text()
                            return await self._handle_steam_form(html, str(buff_resp.url))

                    cookies = self._get_cookies()
                    if cookies:
                        return cookies

                elif location:
                    if self.debug:
                        print(f"[BUFF] Неожиданный редирект: {location[:100]}...")

                    if 'openid/login' in location or 'checkid_setup' in location:
                        async with self.sess.get(
                                location if location.startswith('http') else f"https://steamcommunity.com{location}",
                                proxy=self.proxy,
                                proxy_auth=self.proxy_auth
                        ) as form_resp:
                            if form_resp.status == 200:
                                html = await form_resp.text()

                                if self.debug:
                                    print(f"[BUFF] Получена страница длиной {len(html)} символов")
                                    print("[BUFF] HTML preview:")
                                    print(html[:500])
                                    print("...")

                                    if 'g_steamID' in html:
                                        match = re.search(r'g_steamID = "(\d+)"', html)
                                        if match:
                                            print(f"[BUFF] Обнаружен Steam ID: {match.group(1)}")

                                    if 'submit()' in html:
                                        print("[BUFF] Обнаружена автоматическая отправка формы")

                                hidden_inputs = re.findall(
                                    r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
                                    html,
                                    re.IGNORECASE
                                )

                                if hidden_inputs:
                                    form_data = dict(hidden_inputs)
                                    if self.debug:
                                        print(f"[BUFF] Найдено {len(form_data)} hidden полей")

                                    action_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\']', html,
                                                             re.IGNORECASE)
                                    if action_match:
                                        action = action_match.group(1)
                                        if not action.startswith('http'):
                                            action = f"https://steamcommunity.com{action}"

                                        if self.debug:
                                            print(f"[BUFF] Отправляем форму на: {action}")

                                        async with self.sess.post(
                                                action,
                                                data=form_data,
                                                proxy=self.proxy,
                                                proxy_auth=self.proxy_auth,
                                                allow_redirects=False
                                        ) as submit_resp:
                                            if submit_resp.status in (302, 303):
                                                final_location = submit_resp.headers.get('Location')
                                                if final_location and 'buff.163.com' in final_location:
                                                    # Финальный переход на Buff
                                                    async with self.sess.get(
                                                            final_location,
                                                            proxy=self.proxy,
                                                            proxy_auth=self.proxy_auth,
                                                            allow_redirects=True
                                                    ) as final_resp:
                                                        if self.debug:
                                                            print(f"[BUFF] Финальный переход → {final_resp.status}")

                                                    cookies = self._get_cookies()
                                                    if cookies:
                                                        return cookies

            elif resp.status == 200:
                html = await resp.text()
                if self.debug:
                    print(f"[BUFF] Steam вернул HTML ({len(html)} символов)")
                    print("[BUFF] Начало ответа:")
                    print(html[:300])

        cookies = self._get_cookies()
        if not cookies:
            async with self.sess.get(
                    BUFF,
                    proxy=self.proxy,
                    proxy_auth=self.proxy_auth
            ) as resp:
                if self.debug:
                    print(f"[BUFF] Загрузка главной → {resp.status}")

            cookies = self._get_cookies()

        if not cookies:
            raise RuntimeError("BUFF login failed: не удалось получить session cookie")

        return cookies

    def _get_cookies(self) -> Dict[str, str]:
        cookies = {}
        for cookie in self.sess.cookie_jar:
            domain = str(cookie.get('domain', ''))
            if any(d in domain.lower() for d in ['buff', '163.com', '.163']):
                cookies[cookie.key] = cookie.value
                if self.debug:
                    print(f"[BUFF] Cookie найден: {cookie.key} ({domain})")

        return cookies

    async def _handle_steam_form(self, html: str, current_url: str) -> Dict[str, str]:
        if self.debug:
            print("[BUFF] Обработка формы Steam OpenID")

        form_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>', html,
                               re.IGNORECASE | re.DOTALL)
        if not form_match:
            if self.debug:
                print("[BUFF] Форма не найдена, проверяем авторизацию...")
                # Возможно мы уже авторизованы
                if 'g_steamID' in html and 'g_steamID = "76561199548150646"' in html:
                    print("[BUFF] Steam ID найден, пробуем автоматическую отправку")

        inputs = re.findall(r'<input[^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']', html, re.IGNORECASE)
        form_data = dict(inputs)

        inputs2 = re.findall(r'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for value, name in inputs2:
            if name not in form_data:
                form_data[name] = value

        if form_data and 'openid.mode' in form_data:
            if self.debug:
                print(f"[BUFF] Найдена OpenID форма с {len(form_data)} полями")

            async with self.sess.post(
                    STEAM_POST,
                    data=form_data,
                    proxy=self.proxy,
                    proxy_auth=self.proxy_auth,
                    allow_redirects=False
            ) as resp:
                if self.debug:
                    print(f"[BUFF] Отправка формы → {resp.status}")

                if resp.status in (302, 303):
                    location = resp.headers.get('Location')
                    if location and 'buff.163.com' in location:
                        async with self.sess.get(
                                location,
                                proxy=self.proxy,
                                proxy_auth=self.proxy_auth,
                                allow_redirects=True
                        ) as final_resp:
                            if self.debug:
                                print(f"[BUFF] Финальный переход → {final_resp.status}")
                                print(f"[BUFF] URL: {final_resp.url}")

        cookies = self._get_cookies()
        if cookies:
            return cookies

        raise RuntimeError("Не удалось завершить OpenID авторизацию")

    async def api_get(self, path: str, **params):
        url = BUFF + path
        async with self.sess.get(
                url,
                params=params,
                proxy=self.proxy,
                proxy_auth=self.proxy_auth,
                headers=HEAD_API,
        ) as r:
            if self.debug:
                print(f"[BUFF API] GET {path} → {r.status}")
            data = await r.json(content_type=None)
            if self.debug and r.status != 200:
                print(f"[BUFF API] Response: {data}")
            return data