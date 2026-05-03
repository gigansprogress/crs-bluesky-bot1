import json, os, requests
from bs4 import BeautifulSoup
from atproto import Client
import anthropic

STATE_FILE = "seen_reports.json"
SOURCE_URL = "https://www.everycrsreport.com/reports.html"

def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def fetch_new_reports(seen):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(SOURCE_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    new = []
    for row in soup.select("table tr"):
        link = row.select_one("a[href*='/reports/']")
        if not link:
            continue
        report_id = link["href"].split("/reports/")[-1].strip("/").split(".")[0]
        if report_id in seen:
            continue
        title = link.get_text(strip=True)
        url = "https://www.everycrsreport.com" + link["href"]
        tds = row.select("td")
        abstract = tds[-1].get_text(strip=True)[:500] if len(tds) > 1 else ""
        new.append({"id": report_id, "title": title, "url": url, "abstract": abstract})
    return new

def summarize(report):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = (
        f"Write a 2-sentence plain-English summary of this Congressional Research Service report "
        f"for a general audience. Keep it under 220 characters total.\n\n"
        f"Title: {report['title']}\nAbstract: {report['abstract']}"
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()

def post_to_bluesky(report, summary):
    bsky = Client()
    bsky.login(os.environ["BSKY_HANDLE"], os.environ["BSKY_APP_PASSWORD"])
    text = f"📋 {report['title']}\n\n{summary}\n\n🔗 {report['url']}"
    if len(text) > 298:
        max_title = 298 - len(summary) - len(report['url']) - 12
        text = f"📋 {report['title'][:max_title]}…\n\n{summary}\n\n🔗 {report['url']}"
    bsky.send_post(text=text)
    print(f"Posted: {report['title']}")

def main():
    seen = load_seen()
    new_reports = fetch_new_reports(seen)
    if not new_reports:
        print("No new reports.")
        return
    for report in new_reports[:5]:
        try:
            summary = summarize(report) if os.environ.get("ANTHROPIC_API_KEY") else report["abstract"][:220]
            post_to_bluesky(report, summary)
            seen.add(report["id"])
        except Exception as e:
            print(f"Error on {report['id']}: {e}")
    save_seen(seen)

if __name__ == "__main__":
    main()
