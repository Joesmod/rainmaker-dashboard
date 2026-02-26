"""
Rain Maker Brand Perception — Twitter Collector + Sentiment Scorer
Pulls mentions of @rainmakercorp and @ADoricko via Twitter API v2,
runs rule-based sentiment scoring, outputs dashboard-ready JSON.
"""
import os, json, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from pathlib import Path

# --- Config ---
TARGETS = ["rainmakercorp", "ADoricko"]
KEYWORDS = ["rain maker", "rainmaker corp", "cloud seeding", "weather modification", "Augustus Doricko"]
BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
RAW_DIR = BASE_DIR / "raw"
SCORED_DIR = BASE_DIR / "scored"
DATA_FILE = BASE_DIR / "data.json"

# --- Load token ---
def load_token():
    # Try .env file first
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("TWITTER_BEARER_TOKEN="):
                return line.split("=", 1)[1].strip()
    # Fall back to env var
    return os.environ.get("TWITTER_BEARER_TOKEN")

TOKEN = load_token()
if not TOKEN:
    print("ERROR: No TWITTER_BEARER_TOKEN found in .env or environment")
    sys.exit(1)

# --- Twitter API v2 ---
def twitter_search(query, max_results=100):
    """Search recent tweets via Twitter API v2."""
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,author_id,lang",
        "expansions": "author_id",
        "user.fields": "username,name,public_metrics"
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "RainMakerBrandTracker/1.0"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"Twitter API error {e.code}: {body}")
        return None
    except Exception as e:
        print(f"Request error: {e}")
        return None

def collect_all():
    """Run all search queries and return combined tweets."""
    all_tweets = []
    users_map = {}
    
    # Search for mentions of each target
    queries = [
        f"@rainmakercorp -is:retweet",
        f"@ADoricko -is:retweet",
        f'"rain maker" OR "rainmaker corp" OR "cloud seeding" -is:retweet',
    ]
    
    for query in queries:
        print(f"  Searching: {query}")
        result = twitter_search(query)
        if not result:
            continue
        
        # Build user lookup
        if "includes" in result and "users" in result["includes"]:
            for u in result["includes"]["users"]:
                users_map[u["id"]] = u
        
        if "data" in result:
            for tweet in result["data"]:
                tweet["_query"] = query
                all_tweets.append(tweet)
            print(f"    → {len(result['data'])} tweets")
        else:
            print(f"    → 0 tweets (no data)")
    
    # Dedupe by tweet ID
    seen = set()
    unique = []
    for t in all_tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    
    print(f"\n  Total unique tweets: {len(unique)}")
    return unique, users_map

# --- Sentiment Scoring ---
POSITIVE_WORDS = {
    "great", "amazing", "excellent", "love", "brilliant", "innovative", "solve",
    "solving", "solution", "hero", "impressive", "breakthrough", "future",
    "real deal", "incredible", "fantastic", "support", "proud", "exciting",
    "hope", "helpful", "progress", "success", "positive", "good", "awesome",
    "transformative", "revolutionary", "game changer", "life saving"
}
NEGATIVE_WORDS = {
    "scam", "fraud", "dangerous", "flood", "drought", "blame", "held accountable",
    "conspiracy", "hoax", "unproven", "destroy", "damage", "harm", "risk",
    "lawsuit", "corrupt", "chemtrail", "poison", "terrible", "awful", "worst",
    "reckless", "irresponsible", "fake", "lie", "lies", "grift", "grifter",
    "catastrophe", "disaster", "toxic", "threat", "threatening"
}

def score_sentiment(text):
    """Rule-based sentiment scoring. Returns (label, confidence 0-1)."""
    text_lower = text.lower()
    pos_count = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    
    if pos_count > neg_count:
        return "positive", min(0.5 + pos_count * 0.15, 0.95)
    elif neg_count > pos_count:
        return "negative", min(0.5 + neg_count * 0.15, 0.95)
    else:
        return "neutral", 0.5

def score_tweets(tweets, users_map):
    """Score all tweets and return structured results."""
    scored = []
    for t in tweets:
        text = t.get("text", "")
        label, confidence = score_sentiment(text)
        metrics = t.get("public_metrics", {})
        author_id = t.get("author_id", "")
        user = users_map.get(author_id, {})
        username = user.get("username", "unknown")
        follower_count = user.get("public_metrics", {}).get("followers_count", 0)
        
        reach = (
            metrics.get("retweet_count", 0) * 10 +
            metrics.get("like_count", 0) * 2 +
            metrics.get("reply_count", 0) * 5 +
            metrics.get("quote_count", 0) * 8 +
            follower_count
        )
        
        scored.append({
            "id": t["id"],
            "text": text,
            "username": f"@{username}",
            "author_id": author_id,
            "created_at": t.get("created_at", ""),
            "sentiment": label,
            "confidence": round(confidence, 2),
            "reach": reach,
            "metrics": metrics,
            "follower_count": follower_count
        })
    
    return scored

def compute_brand_score(scored_tweets):
    """Compute 0-100 brand score from scored tweets."""
    if not scored_tweets:
        return 50  # neutral default
    
    total = len(scored_tweets)
    pos = sum(1 for t in scored_tweets if t["sentiment"] == "positive")
    neg = sum(1 for t in scored_tweets if t["sentiment"] == "negative")
    neu = total - pos - neg
    
    # Weighted by reach
    total_reach = sum(t["reach"] for t in scored_tweets) or 1
    pos_reach = sum(t["reach"] for t in scored_tweets if t["sentiment"] == "positive")
    neg_reach = sum(t["reach"] for t in scored_tweets if t["sentiment"] == "negative")
    
    # Brand score: blend of count ratio + reach ratio
    count_score = (pos - neg) / total * 50 + 50
    reach_score = (pos_reach - neg_reach) / total_reach * 50 + 50
    
    score = count_score * 0.4 + reach_score * 0.6
    return max(0, min(100, round(score)))

def build_dashboard_json(scored_tweets, brand_score):
    """Build the dashboard data.json file."""
    total = len(scored_tweets)
    pos = sum(1 for t in scored_tweets if t["sentiment"] == "positive")
    neg = sum(1 for t in scored_tweets if t["sentiment"] == "negative")
    neu = total - pos - neg
    
    # Top mentions sorted by reach
    top_mentions = sorted(scored_tweets, key=lambda t: t["reach"], reverse=True)[:20]
    
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Load existing data to append history
    existing = {"scores": [], "topMentions": []}
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text())
        except:
            pass
    
    # Append today's score (replace if same date)
    scores = [s for s in existing.get("scores", []) if s.get("date") != today]
    scores.append({
        "date": today,
        "score": brand_score,
        "positive": round(pos / total * 100) if total else 0,
        "negative": round(neg / total * 100) if total else 0,
        "neutral": round(neu / total * 100) if total else 0,
        "totalTweets": total
    })
    
    # Detect risk alerts from today's tweets
    risk_alerts = existing.get("riskAlerts", [])
    conspiracy_keywords = ["chemtrail", "weather control", "government", "conspiracy", "hoax", "geo-engineer", "haarp"]
    for t in scored_tweets:
        metrics = t.get("metrics", {})
        replies = metrics.get("reply_count", 0)
        likes = metrics.get("like_count", 0)
        ratio = replies / likes if likes > 0 else 0
        text_lower = t["text"].lower()
        has_conspiracy = any(kw in text_lower for kw in conspiracy_keywords)
        
        if ratio > 0.15 or (t["sentiment"] == "negative" and t["reach"] > 50000) or has_conspiracy:
            severity = "HIGH" if ratio > 0.25 or has_conspiracy else "MEDIUM"
            alert = {
                "severity": severity,
                "type": "auto_detected",
                "post": f"{t['username']} — {t['created_at'][:10]}",
                "text": t["text"][:200],
                "metrics": metrics,
                "replyLikeRatio": round(ratio, 3),
                "reason": f"Reply:like ratio {ratio:.2f}. Reach {t['reach']:,}." + (" Conspiracy keywords detected." if has_conspiracy else ""),
                "date": t["created_at"][:10] if t["created_at"] else today
            }
            # Don't duplicate (check by post key)
            if not any(r.get("post") == alert["post"] for r in risk_alerts):
                risk_alerts.append(alert)

    dashboard = {
        "meta": {
            "lastUpdated": now,
            "targets": ["@rainmakercorp", "@ADoricko"],
            "keywords": ["rain maker", "rainmaker corp", "cloud seeding", "weather modification"]
        },
        "scores": scores[-90:],  # Keep 90 days
        "riskAlerts": risk_alerts[-50:],  # Keep last 50 alerts
        "accountProfiles": existing.get("accountProfiles", {}),
        "aggregate": existing.get("aggregate", {}),
        "topMentions": [
            {
                "user": t["username"],
                "text": t["text"][:280],
                "sentiment": t["sentiment"],
                "reach": t["reach"],
                "date": t["created_at"][:10] if t["created_at"] else today
            }
            for t in top_mentions
        ]
    }
    
    return dashboard

# --- Main ---
def main():
    print("🎯 Rain Maker Brand Tracker — Collecting tweets...\n")
    
    # Create dirs
    RAW_DIR.mkdir(exist_ok=True)
    SCORED_DIR.mkdir(exist_ok=True)
    
    # Collect
    tweets, users_map = collect_all()
    
    if not tweets:
        print("\n⚠️  No tweets collected. Check API token or rate limits.")
        return
    
    # Save raw
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"raw_{ts}.json"
    raw_file.write_text(json.dumps({"tweets": tweets, "users": {k: v for k, v in users_map.items()}}, indent=2))
    print(f"\n  Raw data saved: {raw_file}")
    
    # Score
    scored = score_tweets(tweets, users_map)
    scored_file = SCORED_DIR / f"scored_{ts}.json"
    scored_file.write_text(json.dumps(scored, indent=2))
    print(f"  Scored data saved: {scored_file}")
    
    # Brand score
    brand_score = compute_brand_score(scored)
    print(f"\n  📊 Brand Score: {brand_score}/100")
    
    pos = sum(1 for t in scored if t["sentiment"] == "positive")
    neg = sum(1 for t in scored if t["sentiment"] == "negative")
    neu = len(scored) - pos - neg
    print(f"  ✅ Positive: {pos}  ❌ Negative: {neg}  ➖ Neutral: {neu}")
    
    # Build dashboard JSON
    dashboard = build_dashboard_json(scored, brand_score)
    DATA_FILE.write_text(json.dumps(dashboard, indent=2))
    print(f"\n  Dashboard data updated: {DATA_FILE}")
    
    # Top 5 by reach
    print("\n  📢 Top mentions by reach:")
    for t in sorted(scored, key=lambda x: x["reach"], reverse=True)[:5]:
        emoji = "✅" if t["sentiment"] == "positive" else "❌" if t["sentiment"] == "negative" else "➖"
        print(f"    {emoji} {t['username']} (reach: {t['reach']:,}): {t['text'][:80]}...")
    
    print("\n✅ Collection complete!")

if __name__ == "__main__":
    main()
