import json, os, re, requests
from bs4 import BeautifulSoup
from atproto import Client
import anthropic

CRS_URL = "https://crsreports.congress.gov"
STATE_FILE = "seen_reports.json"

def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def fetch_new_reports(seen):
    resp = requests.get(f"{CRS_URL}/", timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    new = []
    for item in soup.select(".results-list .result-item"):
        link_el = item.select_one("a[href*='/product/']")
        if not link_el:
            continue
        report_id = link_el["href"].split("/product/")[-1].strip("/")
        if report_id in seen:
            continue
        title = link_el.get_text(strip=True)
        url = CRS_URL + link_el["href"]
        abstract = ""
        abs_el = item.select_one(".summary, .abstract, p")
        if abs_el:
            abstract = abs_el.get_text(strip=True)[:500]
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
        model="claude-opus-4-6",
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
