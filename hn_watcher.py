import json
import os
import sys
from pathlib import Path

import requests

CONFIG = {
    "keywords": ["python", "automation", "open source"],
    "min_points": 50,
    "max_alerts_per_run": 5,
    "webhook_url": os.environ.get("WEBHOOK_URL", ""),
    "seen_file": Path(__file__).parent / "seen_stories.json",
}

API_URL = "https://hn.algolia.com/api/v1/search_by_date?query=python&tags=story"


def fetch_stories(keyword: str) -> list[dict]:
    # fetching the 50 most recent stories matching the keyword
    resp = requests.get(
        API_URL,
        params={"query": keyword, "tags": "story", "hitsPerPage": 50},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("hits", [])


def passes_filter(story: dict, cfg: dict) -> bool:
    # keeping only stories that have a title and enough upvotes
    return (story.get("points") or 0) >= cfg["min_points"] and story.get("title")


def load_seen(path: Path) -> set:
    return set(json.loads(path.read_text())) if path.exists() else set()


def save_seen(path: Path, seen: set) -> None:
    path.write_text(json.dumps(sorted(seen)))


def notify(story: dict, webhook_url: str) -> None:
    # building the alert message and posting it to the webhook
    hn_link = f"https://news.ycombinator.com/item?id={story['objectID']}"
    url = story.get("url") or hn_link
    text = (
        f"🔥 **{story['title']}** ({story.get('points', 0)} points)\n"
        f"{url}\n💬 Discussion: {hn_link}"
    )
    # sending both keys since Discord reads "content" and Slack reads "text"
    resp = requests.post(webhook_url, json={"content": text, "text": text}, timeout=15)
    resp.raise_for_status()


def main() -> int:
    cfg = CONFIG
    if not cfg["webhook_url"]:
        print("WARNING: WEBHOOK_URL not set, doing a dry run and printing matches.")

    # collecting stories for every keyword and deduplicating by story id
    stories = {}
    for kw in cfg["keywords"]:
        try:
            for s in fetch_stories(kw):
                stories[s["objectID"]] = s
        except requests.RequestException as e:
            print(f"ERROR fetching '{kw}': {e}")

    # filtering and sorting the highest voted stories to the top
    matched = [s for s in stories.values() if passes_filter(s, cfg)]
    matched.sort(key=lambda s: s.get("points", 0), reverse=True)

    # skipping stories that were already sent in earlier runs
    seen = load_seen(cfg["seen_file"])
    new = [s for s in matched if s["objectID"] not in seen][: cfg["max_alerts_per_run"]]
    print(f"{len(stories)} fetched, {len(matched)} matched, {len(new)} new")

    # notifying for each new story and marking it as seen
    for story in new:
        if cfg["webhook_url"]:
            try:
                notify(story, cfg["webhook_url"])
            except requests.RequestException as e:
                print(f"ERROR notifying: {e}")
                continue
        else:
            print(f"[MATCH] {story['title']} ({story.get('points')} pts)")
        seen.add(story["objectID"])

    save_seen(cfg["seen_file"], seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())