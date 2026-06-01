#!/usr/bin/env python3
"""Небольшой скрипт для проверки API-ключа к /api/agent/search/.

Примеры:
  python3 scripts/check_api_key.py --url http://localhost:8000 --query тест --key <API_KEY>
  python3 scripts/check_api_key.py --url http://localhost:8000 --query тест

Если ключ отсутствует — покажет сообщение сервера об отсутствии ключа.
Если ключ заблокирован — покажет ответ сервера (403 и detail).
Если ключ рабочий — выведет результаты поиска (JSON).
"""
import argparse
import sys
import requests
import json


def main():
    p = argparse.ArgumentParser(description="Test API key against Agent search endpoint")
    p.add_argument("--url", default="http://localhost:8000", help="Base URL of the server")
    p.add_argument("--query", default="тест", help="Search query to send")
    p.add_argument("--key", help="Raw API key (will be sent as Authorization: Bearer <key>)")
    p.add_argument("--xapi", action="store_true", help="Send key in X-API-Key header instead of Authorization")
    args = p.parse_args()

    endpoint = args.url.rstrip("/") + "/api/agent/search/"
    params = {"query": args.query}
    headers = {}
    if args.key:
        if args.xapi:
            headers["X-API-KEY"] = args.key
        else:
            headers["Authorization"] = f"Bearer {args.key}"

    try:
        r = requests.get(endpoint, params=params, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f"Ошибка подключения к {endpoint}: {e}")
        sys.exit(2)

    # Попытка распарсить JSON, иначе вывести текст
    try:
        data = r.json()
    except Exception:
        print(f"Ответ сервера (status={r.status_code}):\n{r.text}")
        sys.exit(1 if r.status_code == 200 else 2)

    if r.status_code == 200:
        print("OK — ключ работает. Вывод результата поиска:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(0)
    elif r.status_code == 401 or r.status_code == 403:
        # Аутентификация/доступ
        detail = data.get("detail") if isinstance(data, dict) else None
        print(f"Доступ запрещён (status={r.status_code}). Сообщение сервера:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(3)
    elif r.status_code == 429:
        print("Слишком много запросов (rate limit). Ответ сервера:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(4)
    else:
        print(f"Неожиданный ответ (status={r.status_code}):")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(5)


if __name__ == "__main__":
    main()
