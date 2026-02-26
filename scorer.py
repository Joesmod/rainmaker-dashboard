#!/usr/bin/env python3
"""
Social Scoring Pipeline
Ingests raw mention JSON (Kah's schema) + existing initial-pull.json,
scores mentions, and outputs merged dashboard JSON.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# --- Config ---
RISK_KEYWORDS = {
    "negative": ["scam", "fraud", "lawsuit", "complaint", "ripped off", "terrible",
                  "sued", "criminal", "ponzi", "ripoff", "avoid", "worst", "fake"],
    "positive": ["love", "recommend", "amazing", "best", "great", "excellent",
                  "incredible", "fantastic", "impressed", "helpful", "brilliant"]
}

ENGAGEMENT_WEIGHTS = {
    "likes": 1,
    "retweets": 3,   # raw schema key
    "reposts": 3,     # initial-pull schema key
    "replies": 5,
    "views": 0.001
}

def score_sentiment(text: str) -> tuple[str, float]:
    """Simple keyword-based sentiment. Returns (label, score -1 to 1)."""
    text_lower = text.lower()
    pos = sum(1 for kw in RISK_KEYWORDS["positive"] if kw in text_lower)
    neg = sum(1 for kw in RISK_KEYWORDS["negative"] if kw in text_lower)
    total = pos + neg
    if total == 0:
        return ("neutral", 0.0)
    score = (pos - neg) / total
    if score > 0.2:
        return ("positive", score)
    elif score < -0.2:
        return ("negative", score)
    return ("mixed", score)

def detect_risk(text: str) -> list[str]:
    """Return list of risk keywords found."""
    text_lower = text.lower()
    return [kw for kw in RISK_KEYWORDS["negative"] if kw in text_lower]

def score_engagement(metrics: dict) -> float:
    """Weighted engagement score."""
    total = 0
    for key, weight in ENGAGEMENT_WEIGHTS.items():
        total += metrics.get(key, 0) * weight
    return round(total, 2)

def score_reach(author_followers: int) -> float:
    """Reach multiplier based on follower count."""
    if author_followers >= 100000:
        return 3.0
    elif author_followers >= 10000:
        return 2.0
    elif author_followers >= 1000:
        return 1.5
    return 1.0

def score_mention(mention: dict) -> dict:
    """Score a single mention from Kah's raw schema."""
    text = mention.get("text", "")
    sentiment_label, sentiment_score = score_sentiment(text)
    risks = detect_risk(text)
    
    engagement = score_engagement({
        "likes": mention.get("likes", 0),
        "retweets": mention.get("retweets", 0),
        "replies": mention.get("replies", 0),
    })
    
    reach = score_reach(mention.get("author_followers", 0))
    composite = round(engagement * reach, 2)
    
    return {
        **mention,
        "sentiment": sentiment_label,
        "sentiment_score": round(sentiment_score, 3),
        "engagement_score": engagement,
        "reach_multiplier": reach,
        "composite_score": composite,
        "risk_keywords": risks,
        "risk_flag": len(risks) > 0
    }

def score_existing_post(post: dict) -> dict:
    """Score a post from the existing initial-pull.json format."""
    text = post.get("content", "")
    metrics = post.get("metrics", {})
    
    sentiment_label, sentiment_score = score_sentiment(text)
    risks = detect_risk(text)
    engagement = score_engagement(metrics)
    
    return {
        **post,
        "sentiment": sentiment_label if not post.get("sentiment") else post["sentiment"],
        "engagement_score": engagement,
        "risk_keywords": risks,
        "risk_flag": post.get("risk_flag", len(risks) > 0)
    }

def ingest_raw(raw_path: Path) -> list[dict]:
    """Ingest and score raw mentions from Kah's schema."""
    with open(raw_path) as f:
        data = json.load(f)
    return [score_mention(m) for m in data.get("mentions", [])]

def process_existing(pull_path: Path) -> dict:
    """Score existing initial-pull.json posts."""
    with open(pull_path) as f:
        data = json.load(f)
    
    scored_posts = [score_existing_post(p) for p in data.get("recentPosts", [])]
    
    # Sort by composite/engagement
    scored_posts.sort(key=lambda p: p.get("engagement_score", 0), reverse=True)
    
    data["recentPosts"] = scored_posts
    
    # Aggregate risk signals from scored posts
    all_risks = set(data.get("riskSignals", []))
    for p in scored_posts:
        if p.get("risk_flag"):
            all_risks.update(p.get("risk_keywords", []))
            all_risks.update(p.get("topics", []))
    data["riskSignals"] = list(all_risks)
    
    return data

def merge_mentions(existing: dict, scored_mentions: list[dict]) -> dict:
    """Merge scored raw mentions into existing dashboard data."""
    # Convert mentions to post format
    for m in scored_mentions:
        post = {
            "account": m.get("author", ""),
            "date": m.get("timestamp", "")[:10] if m.get("timestamp") else "",
            "content": m.get("text", ""),
            "metrics": {
                "replies": m.get("replies", 0),
                "reposts": m.get("retweets", 0),
                "likes": m.get("likes", 0),
            },
            "sentiment": m.get("sentiment", "neutral"),
            "engagement_score": m.get("engagement_score", 0),
            "risk_flag": m.get("risk_flag", False),
            "risk_keywords": m.get("risk_keywords", []),
            "topics": [],  # Could add keyword extraction later
            "source": "mention",
            "url": m.get("url", "")
        }
        existing.setdefault("recentPosts", []).append(post)
    
    # Re-sort all posts by engagement
    existing["recentPosts"].sort(
        key=lambda p: p.get("engagement_score", 0), reverse=True
    )
    
    existing["pulled_at"] = datetime.now().isoformat()
    return existing

def main():
    base = Path(__file__).parent
    pull_path = base / "initial-pull.json"
    raw_dir = base / "raw"
    
    # Score existing data
    if pull_path.exists():
        data = process_existing(pull_path)
        print(f"Scored {len(data.get('recentPosts', []))} existing posts")
    else:
        data = {"recentPosts": [], "accounts": {}}
    
    # Ingest any raw mention files
    if raw_dir.exists():
        for raw_file in sorted(raw_dir.glob("*.json")):
            print(f"Ingesting {raw_file.name}...")
            scored = ingest_raw(raw_file)
            data = merge_mentions(data, scored)
            print(f"  → {len(scored)} mentions scored and merged")
    
    # Write output
    out_path = base / "initial-pull.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Output written to {out_path}")
    
    # Summary
    posts = data.get("recentPosts", [])
    risky = [p for p in posts if p.get("risk_flag")]
    print(f"\nSummary: {len(posts)} total posts, {len(risky)} flagged")
    for p in posts[:5]:
        print(f"  [{p.get('sentiment','?'):8s}] score={p.get('engagement_score',0):>8} | {p.get('content','')[:60]}...")

if __name__ == "__main__":
    main()
