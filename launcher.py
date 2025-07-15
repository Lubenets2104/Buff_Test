import asyncio
from steam import SteamClient
from buff import BuffClient
# Прокси
IP = ""  # Сюда IP
PORTS = range(10000, 10010) # Порты
USER = "ElvD8dHvWuawukEaOLFD" # Логин от прокси
PASS = "RNW78Fm5" # Пароль от прокси
# Стим
LOGIN = "" # Логин
PWD = "" # Пароль
MAFILE = ".maFile"

async def try_port(port: int, debug: bool = True) -> bool:
    proxy = f"http://{USER}:{PASS}@{IP}:{port}"
    print(f"\n{'=' * 60}")
    print(f"Пробуем порт {port}: {proxy}")
    print('=' * 60)

    steam = SteamClient(LOGIN, PWD, MAFILE, proxy=proxy, debug=debug)
    try:
        await steam.login()
        print("Steam авторизация успешна")

        if debug:
            print("\nПроверка Steam cookies:")
            important_cookies = ['sessionid', 'steamLoginSecure', 'steamMachineAuth']
            for cookie in steam.sess.cookie_jar:
                if any(name in cookie.key for name in important_cookies):
                    print(f"  - {cookie.key}: {cookie.value[:20]}... ({cookie.get('domain')})")

        buff = BuffClient(steam, debug=debug)
        cookies = await buff.login()
        print(f"BUFF авторизация успешна (cookies: {list(cookies.keys())})")

        print("\nПроверка авторизации Buff:")
        try:
            data = await buff.api_get("/api/market/goods?game=csgo&page_num=1")
            print("Баланс аккаунта:", data)
        except Exception as e:
            print("Ошибка при получении баланса:", e)

        try:
            data = await buff.api_get("/api/market/goods",
                                      game="csgo",
                                      page_num=1,
                                      page_size=1
                                      )
            if data.get('code') == 'OK':
                print("API /api/market/goods - OK")
                return True
            else:
                print(f"API вернул: {data.get('code', 'Unknown')}")
        except Exception as e:
            print(f"Ошибка API: {e}")

        try:
            steam_id = getattr(steam, 'steam_id', '76561199548150646')
            data = await buff.api_get("/api/market/steam_inventory",
                                      game="csgo",
                                      force="0"
                                      )
            if data.get('code') == 'OK':
                print("API steam_inventory - OK")
                return True
            elif data.get('code') == 'Login Required':
                print("API говорит: требуется авторизация")
            else:
                print(f"API вернул: {data}")
        except Exception as e:
            print(f"Ошибка: {e}")

        try:
            async with buff.sess.get(
                    "https://buff.163.com/api/market/goods?game=csgo&page_num=1",
                    proxy=buff.proxy,
                    proxy_auth=buff.proxy_auth,
                    headers={"X-Requested-With": "XMLHttpRequest"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 'OK':
                        print("Прямой запрос к API - OK")
                        print(f"\nУСПЕХ! Порт {port} работает полностью")
                        return True
        except:
            pass

        if cookies:
            print(f"\nПорт {port}: авторизация прошла, но API не работает")
            print("Возможно, требуется дополнительная проверка или другой endpoint")
            return False

    except Exception as e:
        print(f"Ошибка: {type(e).__name__}: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        return False
    finally:
        await steam.close()

async def main():
    print("Начинаем поиск рабочего порта...\n")

    working_ports = []

    for p in PORTS:
        if await try_port(p, debug=True):
            working_ports.append(p)
            print(f"\nНайден полностью рабочий порт: {p}")
            break

    if not working_ports:
        print("\nНе найдено портов с полной функциональностью")
        print("Но некоторые порты могут работать частично (авторизация проходит)")
    else:
        print(f"\nИтого рабочих портов: {len(working_ports)}")
        print(f"Рекомендуется использовать порт: {working_ports[0]}")

if __name__ == "__main__":
    asyncio.run(main())
