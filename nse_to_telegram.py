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
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def create_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
            "Connection": "keep-alive",
        }
    )
    return s


def find_csv_url(session: requests.Session) -> str:
    home = session.get("https://www.nseindia.com/", timeout=30)
    home.raise_for_status()
    time.sleep(1)

    page = session.get(NSE_PAGE, timeout=30)
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".csv" in href.lower():
            return urljoin("https://www.nseindia.com", href)

    m = re.search(r'https?://[^"\']+\.csv[^"\']*', page.text, flags=re.IGNORECASE)
    if m:
        return m.group(0)

    raise RuntimeError("Could not find CSV link on NSE page. NSE may have changed page structure.")


def download_csv(session: requests.Session, csv_url: str, out_file: str) -> None:
    r = session.get(csv_url, timeout=60, stream=True)
    r.raise_for_status()

    with open(out_file, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def send_to_telegram(bot_token: str, chat_id: str, file_path: str, caption: str = "") -> None:
    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f, "text/csv")}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(telegram_url, data=data, files=files, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API returned not ok: {payload}")


def main():
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")

    session = create_nse_session()
    csv_url = find_csv_url(session)
    print(f"Found CSV URL: {csv_url}")

    now_utc = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = f"nse_live_market_indices_{now_utc}.csv"

    download_csv(session, csv_url, out_file)
    print(f"Downloaded file: {out_file}")

    caption = f"NSE CSV sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    send_to_telegram(bot_token, chat_id, out_file, caption)
    print("CSV sent to Telegram successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
