# Rain Maker — Social Scoring Dashboard

Brand perception tracker for Rain Maker. Monitors sentiment across Twitter mentions, replies, and relevant conversations.

## Target Accounts
- **@rainmakercorp** — Rain Maker company account
- **@ADoricko** — CEO Augustus Doricko

## How It Works
- `data.json` — Updated daily by the data collection pipeline
- `index.html` — Static dashboard, deployed via GitHub Pages
- Charts: Brand score over time + sentiment breakdown (positive/negative/neutral)
- Top mentions feed with reach and sentiment badges

## Data Format
```json
{
  "scores": [{"date": "2026-02-25", "score": 72, "positive": 45, "negative": 12, "neutral": 31}],
  "topMentions": [{"user": "@example", "text": "...", "sentiment": "positive", "reach": 5000}]
}
```

## Deployment
GitHub Pages — push to `main`, enable Pages from repo settings.

## Built by
Gumbo · Scopey (dashboard) · Kah (data pipeline)
