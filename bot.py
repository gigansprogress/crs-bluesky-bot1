import json, os, requests, csv, io
from atproto import Client
import anthropic

STATE_FILE = "seen_reports.json"
CSV_URL = "https://www.everycrsreport.com/reports.csv"

def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def fetch_new_reports(seen):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CRSBot/1.0)"}
    resp = requests.get(CSV_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    # CSV is newest-first; take first 50 rows to check for new ones
    new = []
    for row in rows[:50]:
        report_id = row.get("number", "").strip()
        if not report_id or report_id in seen:
            continue
        title = row.get("title", "").strip()
        url = f"https://www.everycrsreport.com/reports/{report_id}.html"
        new.append({"id": report_id, "title": title, "url": url, "abstract": title})
    return new

def summarize(report):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = (
        f"Write 1-2 sentences in plain English describing what this Congressional Research Service "
        f"report is about, for a general audience. Keep it under 200 characters.\n\n"
        f"Title: {report['title']}"
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
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
            summary = summarize(report) if os.environ.get("ANTHROPIC_API_KEY") else report["title"]
            post_to_bluesky(report, summary)
            seen.add(report["id"])
        except Exception as e:
            print(f"Error on {report['id']}: {e}")
    save_seen(seen)

if __name__ == "__main__":
    main()
