# Stress Test Report

## Current Request Path

The production default is browser-first with one reusable warmed Firefox context/page. Direct HTTP was reverse-engineered but is disabled by default because Google returns a retry/enablejs shell in the current environment. Re-enable it only for future reverse-engineering with:

```bash
export LENS_USE_DIRECT_HTTP=1
```

Default successful responses should show:

```text
X-Google-Lens-Source: playwright_firefox
X-Google-Lens-Direct-Attempt: skipped
```

The FastAPI server lazily starts the Playwright persistent context once, keeps one page open, and serializes requests with an `asyncio.Lock`. The browser closes only during FastAPI shutdown.

## Observed Run

External public 300-request test:

```text
path: Dark Mac on external connection -> Cloudflare Tunnel -> Pink Mac server -> Google Lens
total: 300
valid_pages: 297
valid_pages_with_results: 290
no_match_pages: 7
true_failures: 3
captcha_pages: 3
average_latency: 5.242s
p95_latency: 7.132s
max_latency: 48.158s
success_rate: 99.0%
requests_per_hour_estimate: 682.6
```

Interpretation: the public tunnel path is validated from a separate machine. Latency and error rate are within challenge requirements, with captcha/unusual-traffic risk as the main remaining limitation.

Latest 1000-style sequential run:

```text
command: python3 experiments/batch_test_urls.py --limit 1000 --concurrency 1
attempted_target: 1000
stopped_early_at: 686
stop_reason: captcha/unusual traffic appeared 4 times
valid_pages: 680
valid_pages_with_results: 667
no_match_pages: 13
true_failures: 6
captcha_pages: 4
average_latency: 2.298s
p95_latency: 2.377s
success_rate: 99.1%
requests_per_hour_estimate: 1556.9
```

Interpretation: the API exceeded the challenge's 300+ valid HTML threshold before early stop and exceeded the latency requirement. The main scaling limitation is Google captcha/unusual-traffic risk, not local browser startup cost.

Current reusable-page 100-request run:

```text
command: python3 experiments/batch_test_urls.py --limit 100
valid_pages: 100
valid_pages_with_results: 97
no_match_pages: 3
true_failures: 0
captcha_pages: 0
average_latency: 1.741s
max_latency: 3.057s
p95_latency: 2.333s
success_rate: 100%
requests_per_hour_estimate: 2049.7
```

Current reusable-page 20-request run:

```text
command: python3 experiments/batch_test_urls.py --limit 20
valid_pages: 20
valid_pages_with_results: 19
no_match_pages: 1
true_failures: 0
captcha_pages: 0
average_latency: 1.658s
max_latency: 2.840s
p95_latency: 2.139s
success_rate: 100%
requests_per_hour_estimate: 2155.0
```

Latency comparison:

| Mode | Average latency |
| --- | ---: |
| Direct + browser fallback | 10.113s |
| Browser-first, new window/context per request | 6.808s |
| Browser-first, reusable warmed page, 100-run | 1.741s |
| Browser-first, reusable warmed page, 1000-style run | 2.298s |

The reusable-page path removes browser startup/shutdown from each request and avoids the intermediate visible `udm=26` page. It still uses one shared page and concurrency `1`.

Current browser-first 20-request run after disabling direct HTTP by default:

```text
command: python3 experiments/batch_test_urls.py --limit 20
valid_pages: 20
valid_pages_with_results: 19
no_match_pages: 1
true_failures: 0
captcha_pages: 0
average_latency: 8.110s
max_latency: 9.626s
p95_latency: 9.596s
success_rate: 100%
requests_per_hour_estimate: 443.1
```

This is faster than the earlier 100-request sequential average of 10.113s/request because the default path now skips the failing direct HTTP attempt.

## Prior 100-Request Run

Command:

```bash
python3 experiments/batch_test_urls.py --limit 100
```

Observed summary:

```text
total: 100
valid_pages: 99
valid_pages_with_results: 97
no_match_pages: 2
true_failures: 1
captcha_pages: 0
average_latency: 10.113s
max_latency: 14.397s
p95_latency: 12.489s
success_rate: 99%
```

The one true failure was an upstream image fetch/navigation failure, not a Google captcha.

## Concurrency 2 Test

Command:

```bash
python3 experiments/batch_test_urls.py --limit 50 --concurrency 2
```

Observed summary:

```text
total: 50
valid_pages: 0
valid_pages_with_results: 0
no_match_pages: 0
true_failures: 50
captcha_pages: 1
average_latency: 6.056s
max_latency: 192.681s
p95_latency: 4.202s
success_rate: 0%
failure_reasons:
  validation_failed: 48
  browser_navigation_failed: 1
  captcha: 1
```

Conclusion: concurrency 2 with one persistent Firefox profile is not stable. It caused browser/profile contention and produced 0% valid pages. This result invalidates using one warmed profile concurrently.

## Sequential Throughput

Using the latest 1000-style run average latency:

```text
3600 seconds/hour / 2.298 seconds/request = 1566.6 requests/hour
```

Estimated maximum sequential throughput:

```text
~1,557 requests/hour observed estimate
```

This estimate came from 686 completed requests before captcha/unusual-traffic early stop.

## Concurrency Estimates

The current implementation uses one shared page protected by a lock, so increasing client concurrency does not increase throughput for one server process. Requests queue behind the shared page.

| Client concurrency | Effective browser concurrency | Estimated req/hour |
| ---: | ---: |
| 1 | 1 | ~1,557 |
| 2 | 1 | ~1,557 |
| 5 | 1 | ~1,557 |
| 10 | 1 | ~1,557 |

Scaling above one effective browser worker would require isolated warmed browser profiles in separate processes or containers. The older concurrency 2 test without the shared-page lock failed with 0% success due to browser/profile contention.

## Expected Bottlenecks

- Single persistent Firefox profile: current reliable path is serialized around one warmed browser profile and one shared page.
- Browser/profile contention: the shared lock prevents concurrent page use, but separate concurrent workers would need isolated profiles.
- Page navigation cost: each request still gets a Lens redirect and navigates Google Search Exact Matches.
- Google challenge behavior: repeated Lens/Search requests from one IP/profile can trigger retry shells, unusual-traffic pages, or captcha.
- Upstream image fetches: bad, rate-limited, or blocked image URLs fail before Lens upload.
- CPU/memory pressure: multiple headed Firefox contexts would be expensive locally.
- Session/profile contention: concurrent requests sharing one profile risk corrupt state, tab collisions, and inconsistent cookies.

## Captcha Risk Factors

Likely captcha triggers:

- High request rate from one IP.
- Many repeated Google Lens/Search navigations in a short window.
- Headless or automation-looking browser behavior.
- Fresh profiles without human interaction history.
- Multiple concurrent browser contexts using the same Google/IP state.
- Reusing the same query/image patterns.
- Failed/retry navigation loops.

The persistent headed profile helps because captcha/consent can be solved once and reused, but it does not remove rate-limit risk.

## Can This Pass 1000 Requests in 1 Hour?

With the current architecture at concurrency 1, the latest 1000-style run showed:

```text
~1,557 requests/hour estimate from 686 completed requests
```

The local browser architecture is fast enough for 1000 requests/hour on latency, but the actual run stopped early at 686 because captcha/unusual traffic appeared 4 times.

Mathematically, the observed average gives:

```text
1000 requests * 2.298 seconds/request = 2298 seconds = 38.3 minutes
```

Operational caveat: Google challenge behavior stopped the run before 1000. The implementation still depends on a warmed local profile and one IP.

Practical conclusion:

```text
Current architecture: fast enough at effective concurrency 1, but not proven to survive a full 1000-request run without captcha.
```

Current practical throughput is about:

```text
~1,557 requests/hour per warmed reusable-page worker before captcha early stop
```

If this estimate degrades under a longer run, the scaling path remains isolated warmed workers:

```text
separate browser profile + separate process/container + conservative per-worker queue
```

To harden beyond local proof-of-concept, the design would need request scheduling, backoff, captcha detection, per-profile rate limits, and probably separate exit IPs. Even then, Google challenge behavior would remain the main reliability risk.

Do not claim fully proven 1000-request reliability until a 1000-request run passes without captcha early stop. The implementation did meet the challenge's 300+ valid HTML threshold in this run.
