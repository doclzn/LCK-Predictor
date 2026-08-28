# V25 — Root Cause Review

## Why the user could see “no change” at all

The V24 database/API itself was checked and was already returning:

- live: none;
- upcoming: 21/08 BRO–BFX, 21/08 KT–T1, then 22/08 and 23/08;
- HLE 2–0 DK and NS 2–0 KRX as completed results on 20/08.

Therefore, seeing **HLE × DK as current/future together with exactly the old tiny typography** meant the browser was not actually displaying the V24 server.

### Root cause
All historical builds used the same fixed local origin:

`http://localhost:8765`

If an older LCK Predictor server remained open, a newer server could fail to bind to 8765 while the browser tab kept talking to the old process. Service-worker/static browser caches made this harder to notice.

This explains both symptoms simultaneously:

1. old HLE × DK state;
2. typography apparently unchanged.

## V25 fixes

### New isolated port
V25 uses:

`http://localhost:8825`

It does not share the origin with V10–V24.

### Visible version proof
The top bar must visibly say:

`V25 • PORTA 8825 • NOVA INTERFACE`

The browser also calls `/api/health`. If the returned server version is not `V25_FRESH_UI`, the UI stops and displays a full-screen “Versão antiga detectada” warning.

### Cache removal
- static files use `Cache-Control: no-store`;
- old service workers are unregistered;
- Cache Storage is cleared;
- V25 service worker is network-only;
- CSS/JS URLs contain a unique V25 build query.

### Match-state validation
At startup V25 runs schedule-schema validation and stale-schedule pruning. The packaged API was regression-tested to return:

- no HLE × DK in live;
- no 20/08 entry in upcoming;
- KT × T1 present on 21/08;
- HLE × DK present only in completed history.

### Typography
The prior dashboard lineage used many 5–10 px labels. V25 adds a final readability layer:

- default root scale: 26 px (`Máxima`);
- normal body: 20 px;
- nav: ~19–20 px;
- match team names: 21 px;
- match score: 23 px;
- secondary text: 16–18 px;
- page titles: 38 px;
- hero title: 39 px.

This is intentionally aggressive. The goal is to be visibly different, not subtly larger.
