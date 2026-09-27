# Measurement wiring 2026-09-27

How the measurement leg works, how to schedule it on the host, the leading
indicators it feeds, and the plan's kill criteria as the operator's watch list.
Scheduling is a HOST action: the agent installs nothing system-wide.

---

## 1. What is wired

`scripts/measure_daily.sh`:

```
scripts/measure_daily.sh <VIDEO_ID> [--mock] [--api-base URL] [--force]
```

It runs `python3 -m shortform measure --video-id <VIDEO_ID>`, which calls:

```
GET https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=<VIDEO_ID>&key=$YOUTUBE_API_KEY
```

The command appends one JSON snapshot to `data/metrics/<VIDEO_ID>.jsonl`, then the
script prints one line:

```
[OK] <VIDEO_ID> views=... likes=... comments=... placeholder=...% source=... fetched_at=...
```

Guards against double runs:

* one snapshot per video per UTC calendar day (override with `--force`);
* a `flock` so two concurrent cron firings cannot both append.

`data/metrics/` is gitignored; the snapshots stay local.

The public Data API exposes views/likes/comments only. The retention/CTR numbers
need the YouTube Analytics API with OAuth; `measure` emits a clearly labelled
`view_through_placeholder_pct` (a like/comment/view proxy) and must never be
reported as retention.

---

## 2. Proof run against the local mock (raw)

Mock started on port 8791 with the default transcript:

```bash
python3 mocks/youtube_mock.py --port 8791 --transcript mocks/transcript.log &
```

Run 1 (fresh: appends):

```text
$ bash scripts/measure_daily.sh MOCKID123 --mock --api-base http://127.0.0.1:8791
GET http://127.0.0.1:8791/youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=MOCK_KEY
title: How Roman concrete survived 2000 years #Shorts
views: 12874
likes: 1043
comments: 87
view_through_placeholder_pct: 8.784
snapshot appended to /opt/workspace/shortform-studio/data/metrics/MOCKID123.jsonl
[OK] MOCKID123 views=12874 likes=1043 comments=87 placeholder=8.784% source=mock fetched_at=2026-09-27T04:35:51Z
RUN1_EXIT=0
```

Run 2 the same UTC day (guard skips):

```text
$ bash scripts/measure_daily.sh MOCKID123 --mock --api-base http://127.0.0.1:8791
[SKIP] MOCKID123 already measured for 2026-09-27; use --force to run again
RUN2_EXIT=0
```

Raw appended jsonl line (`data/metrics/MOCKID123.jsonl`):

```json
{"fetched_at": "2026-09-27T04:35:51Z", "video_id": "MOCKID123", "source": "mock", "api_base": "http://127.0.0.1:8791", "title": "How Roman concrete survived 2000 years #Shorts", "channelTitle": "OmniStack Mock Channel", "statistics": {"viewCount": "12874", "likeCount": "1043", "favoriteCount": "0", "commentCount": "87"}, "view_through_placeholder_pct": 8.784, "view_through_note": "Placeholder derived from public likes/comments/views; the real view-through rate requires the YouTube Analytics API (OAuth)."}
```

Raw mock transcript lines appended (`mocks/transcript.log`):

```text
2026-09-27T04:35:51Z pid=10398 SESSION START mock listening on http://127.0.0.1:8791 transcript=mocks/transcript.log
2026-09-27T04:35:51Z pid=10398 REQUEST GET /youtube/v3/videos?part=snippet%2Cstatistics&id=MOCKID123&key=MOCK_KEY HTTP/1.1
2026-09-27T04:35:51Z pid=10398   Accept-Encoding: identity
2026-09-27T04:35:51Z pid=10398   Host: 127.0.0.1:8791
2026-09-27T04:35:51Z pid=10398   User-Agent: Python-urllib/3.11
2026-09-27T04:35:51Z pid=10398   Connection: close
2026-09-27T04:35:51Z pid=10398 RESPONSE 200 {} body=466 bytes
```

The mock was killed after the run and no mock process remained.

Note: the transcript logs the request URL verbatim, including `key=`. The mock run
used the dummy key `MOCK_KEY`. On a real host, keep `mocks/transcript.log` out of
git once a real `YOUTUBE_API_KEY` is used.

---

## 3. Scheduling from the host (operator action)

The agent does not install anything system-wide. Pick one option.

### Option A: cron

Keep the API key in a host-only, root-owned `0600` file outside the repo, for
example `/etc/omniagent/youtube.env`:

```sh
export YOUTUBE_API_KEY="<real key>"
```

Add one crontab line (daily at 06:17 host time):

```cron
17 6 * * *  cd /opt/workspace/shortform-studio && . /etc/omniagent/youtube.env && scripts/measure_daily.sh <REAL_VIDEO_ID> >> data/metrics/cron.log 2>&1
```

Verify: `tail -n 5 data/metrics/<REAL_VIDEO_ID>.jsonl` grows by one line per day.

### Option B: systemd timer

`/etc/systemd/system/shortform-measure.service`:

```ini
[Unit]
Description=shortform-studio daily measurement snapshot

[Service]
Type=oneshot
WorkingDirectory=/opt/workspace/shortform-studio
EnvironmentFile=/etc/omniagent/youtube.env
ExecStart=/opt/workspace/shortform-studio/scripts/measure_daily.sh <REAL_VIDEO_ID>
```

`/etc/systemd/system/shortform-measure.timer`:

```ini
[Unit]
Description=Daily shortform-studio measurement

[Timer]
OnCalendar=*-*-* 06:17:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and verify:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shortform-measure.timer
systemctl list-timers shortform-measure.timer
```

Never put the key value in the repo or in a world-readable crontab. Rotate it if it
is ever exposed.

---

## 4. Leading indicators this feeds

| # | Indicator family | What we watch | Measurement source | Frequency |
| --- | --- | --- | --- | --- |
| 1 | Views and engagement | `viewCount`, `likeCount`, `commentCount`; engagement rate `(likes+comments)/views` | YouTube Data API v3 `videos.list` statistics, collected by `scripts/measure_daily.sh` | Daily |
| 2 | Retention and CTR | average view duration %, average percentage viewed, thumbnail CTR | YouTube Studio > Analytics, **manual**. The public Data API does not expose these; `view_through_placeholder_pct` is a placeholder, not retention | Weekly |
| 3 | Subscriber growth | net subscribers, acquisition rate | YouTube Studio > Analytics > Audience, **manual** | Weekly / monthly |
| 4 | Production cost per video | wall-clock and cash cost per video | our own logs: `out/<slug>/provenance.json` command durations; review cost table | Weekly |
| 5 | Policy compliance | warnings/strikes count, AI disclosure accuracy | YouTube Studio notifications plus human audit after each upload; **target 0** | Ongoing |
| 6 | Affiliate CTR (post-MVP) | link clicks, conversion rate, earnings per click | affiliate program dashboard plus tracking IDs. Status: **UNKNOWN**, not wired; no affiliate link exists yet | Weekly / bi-weekly |

Do not expose indicator 2's placeholder as retention.

---

## 5. Kill criteria (verbatim from the plan, the operator's watch list)

1. **Low Engagement**
   * **Detection:** Consistently low Avg View Duration (<20%), low CTR (<1%), stagnant/declining subscribers/followers.
   * **Kill Criterion:** No significant improvement after 3 months of strategic adjustments.

2. **Platform Policy Violations**
   * **Detection:** Platform warnings/strikes, monetization loss, human audit.
   * **Kill Criterion:** Multiple strikes (e.g. 2-3 YouTube strikes in 90 days), permanent demonetization/account termination.

3. **Insufficient Revenue / Unprofitable**
   * **Detection:** Monthly tracking of revenue vs. costs. Consistent losses (>200% costs of revenue) for 6 months after monetization.
   * **Kill Criterion:** Remains unprofitable for >12 months with no clear path to growth after cost/strategy optimization.

4. **Technical / API Failures**
   * **Detection:** Agent logs (API errors), monitoring dashboards (failed uploads), missing content.
   * **Kill Criterion:** Persistent, unresolvable issues halting production for >1 week, or recurrent failures requiring constant manual intervention.

Source: `/opt/omni/data/research/money/plan-p2-short-form-channels-2026-09-27.md`
section "Main Failure Modes Each with Detection + Kill Criterion".

In short, the four stop rules are: **3 months no improvement; 2-3 strikes; still
unprofitable after >12 months; production halted >1 week.**
