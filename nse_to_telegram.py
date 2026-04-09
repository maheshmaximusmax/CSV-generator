import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

NSE_PAGE = "https://www.nseindia.com/market-data/live-market-indices"

# Retry settings
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 5


def get_env(name: str, required: bool = True, default: str = "") -> str:
    v = os.getenv(name, default).strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


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


def with_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                print(f"[WARN] Attempt {attempt} failed: {e}. Retrying in {RETRY_WAIT_SECONDS}s...")
                time.sleep(RETRY_WAIT_SECONDS)
            else:
                print(f"[ERROR] Final attempt failed: {e}")
    raise last_err


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

    match = re.search(r'https?://[^"\']+\.csv[^"\']*', page.text, flags=re.IGNORECASE)
    if match:
        return match.group(0)

    raise RuntimeError("Could not locate CSV URL on NSE page.")


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
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f, "text/csv")}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, data=data, files=files, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Telegram sendDocument HTTP {resp.status_code}: {resp.text}")

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram sendDocument not ok: {payload}")


def telegram_send_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram sendMessage HTTP {resp.status_code}: {resp.text}")
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram sendMessage not ok: {payload}")


def run():
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    send_success_text = get_env("SEND_SUCCESS_TEXT", required=False, default="false").lower() == "true"

    session = build_session()

    csv_url = with_retry(find_csv_url, session)
    print(f"[INFO] CSV URL: {csv_url}")

    file_path = with_retry(download_csv, session, csv_url)
    print(f"[INFO] Downloaded: {file_path}")

    caption = f"NSE CSV | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    with_retry(telegram_send_document, bot_token, chat_id, file_path, caption)
    print("[INFO] File sent to Telegram")

    if send_success_text:
        with_retry(
            telegram_send_message,
            bot_token,
            chat_id,
            "✅ NSE CSV delivered successfully."
        )
        print("[INFO] Success message sent")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        # try to send failure alert
        try:
            bt = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            cid = os.getenv("TELEGRAM_CHAT_ID", "").strip()
            if bt and cid:
                fail_text = f"❌ NSE CSV job failed.\nReason: {str(e)}\nUTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
                telegram_send_message(bt, cid, fail_text)
                print("[INFO] Failure alert sent to Telegram")
        except Exception as alert_err:
            print(f"[WARN] Could not send failure alert: {alert_err}", file=sys.stderr)

        sys.exit(1)
