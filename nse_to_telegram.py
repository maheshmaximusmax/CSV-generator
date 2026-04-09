import argparse
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


NSE_PAGE = "https://www.nseindia.com/market-data/live-market-indices"


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    })
    return s


def find_csv_url(session: requests.Session) -> str:
    # warmup for cookies
    r1 = session.get("https://www.nseindia.com/", timeout=30)
    r1.raise_for_status()
    time.sleep(1)

    r2 = session.get(NSE_PAGE, timeout=30)
    r2.raise_for_status()

    soup = BeautifulSoup(r2.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".csv" in href.lower():
            return urljoin("https://www.nseindia.com", href)

    regex_match = re.search(r'https?://[^"\']+\.csv[^"\']*', r2.text, flags=re.IGNORECASE)
    if regex_match:
        return regex_match.group(0)

    raise RuntimeError("Could not locate CSV URL on NSE page. Website structure may have changed.")


def download_csv(session: requests.Session, csv_url: str) -> str:
    filename = f"nse_live_market_indices_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    r = session.get(csv_url, timeout=60, stream=True)
    r.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return filename


def telegram_send_document(bot_token: str, chat_id: str, file_path: str, caption: str = "") -> None:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f, "text/csv")}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(api_url, data=data, files=files, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API HTTP {resp.status_code}: {resp.text}")

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API returned error payload: {payload}")


def run_job() -> None:
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")

    session = build_session()
    csv_url = find_csv_url(session)
    print(f"[INFO] CSV URL found: {csv_url}")

    file_path = download_csv(session, csv_url)
    print(f"[INFO] CSV downloaded: {file_path}")

    caption = f"NSE CSV | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    telegram_send_document(bot_token, chat_id, file_path, caption=caption)
    print("[INFO] CSV sent to Telegram successfully")


def main():
    parser = argparse.ArgumentParser(description="Download NSE CSV and send to Telegram channel")
    parser.parse_args()

    try:
        run_job()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
