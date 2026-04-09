import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

NSE_PAGE = "https://www.nseindia.com/market-data/live-market-indices"
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 5


def _session() -> requests.Session:
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


def _with_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS)
    raise RuntimeError(f"All {MAX_RETRIES} attempts failed. Last error: {last_err}")


def _find_csv_url(session: requests.Session) -> str:
    home = session.get("https://www.nseindia.com/", timeout=30)
    home.raise_for_status()
    time.sleep(1)

    page = session.get(NSE_PAGE, timeout=30)
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".csv" in href.lower():
            return urljoin("https://www.nseindia.com", href)

    m = re.search(r'https?://[^"\']+\.csv[^"\']*', page.text, flags=re.IGNORECASE)
    if m:
        return m.group(0)

    raise RuntimeError("Could not find CSV URL on NSE page.")


def find_csv_url() -> str:
    session = _session()
    return _with_retry(_find_csv_url, session)


def _download_csv(session: requests.Session, csv_url: str, filename: str) -> str:
    r = session.get(csv_url, timeout=60, stream=True)
    r.raise_for_status()
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return filename


def download_csv(csv_url: str) -> str:
    session = _session()
    filename = f"nse_live_market_indices_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _with_retry(_download_csv, session, csv_url, filename)


def send_to_telegram(file_path: str, caption: str = "") -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (os.path.basename(file_path), f, "text/csv")}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, data=data, files=files, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")

    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API not ok: {result}")


def send_failure_alert(message: str) -> None:
    """Send a failure alert to Telegram as a text message."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return  # silently skip if creds not set

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = (
        f"❌ NSE CSV job failed.\n"
        f"Reason: {message}\n"
        f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=30)
    except Exception:
        pass  # best-effort alert


def run_full_job() -> dict:
    csv_url = find_csv_url()
    file_path = download_csv(csv_url)
    caption = f"NSE CSV {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    send_to_telegram(file_path, caption=caption)
    return {"csv_url": csv_url, "file_path": file_path}
