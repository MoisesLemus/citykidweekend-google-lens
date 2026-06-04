# Stress Test Report

## Observed Run

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

## Sequential Throughput

Using the observed average latency:

```text
3600 seconds/hour / 10.113 seconds/request = 355.9 requests/hour
```

Estimated maximum sequential throughput:

```text
~356 requests/hour
```

## Idealized Concurrency Estimates

These estimates assume latency remains flat and requests do not interfere with each other. That is unlikely with the current persistent-browser design, but the math gives an upper bound.

| Concurrency | Estimated req/hour |
| ---: | ---: |
| 1 | ~356 |
| 2 | ~712 |
| 5 | ~1,780 |
| 10 | ~3,559 |

## Expected Bottlenecks

- Single persistent Firefox profile: current reliable path is effectively serialized around one warmed browser profile.
- Browser startup/navigation cost: each fallback request drives Google/Lens/Search UI and waits for page content.
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

With the current architecture at concurrency 1:

```text
~356 requests/hour
```

So it cannot realistically complete 1000 requests in 1 hour sequentially.

Mathematically, concurrency 3 would be enough:

```text
1000 / 356 = 2.81
```

But operationally, the current implementation is not designed for safe concurrent browser fallback. Concurrency 2 might work experimentally, but concurrency 5 or 10 would likely increase captcha risk and browser/profile contention.

Practical conclusion:

```text
Current architecture: reliable for low-rate local testing, not suitable for 1000 requests/hour.
```

To target 1000 requests/hour, the design would need a pool of isolated warmed browser profiles, request scheduling, backoff, captcha detection, per-profile rate limits, and probably multiple exit IPs. Even then, Google challenge behavior would remain the main reliability risk.
