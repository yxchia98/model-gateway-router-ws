# APJ AI Innovation Hub — NeMo Switchyard routing demo

A standalone Switchyard v0.4.0a1 gateway and a Dell-inspired frontend that
showcase routing methods. All configured upstream models use free OpenRouter
endpoints. The gateway runs the native server from the pinned Python wheel.

## Start and open

```bash
cd /home/ubuntu/code/model-gateway-router-ws/nemo-switchyard
# Set OPENROUTER_API_KEY in the private .env first.
docker compose up -d --build --wait --wait-timeout 180
```

- Frontend: **http://172.16.247.63:3002** (or http://localhost:3002 on the host)
- API: http://172.16.247.63:4002/v1

Ports bind to `0.0.0.0` for this protected lab. Change `FRONTEND_PORT` and
`SWITCHYARD_PORT` in `.env` when needed. The frontend proxies requests to the
gateway and receives no OpenRouter credential. Neither demo service has user
authentication; use a trusted network or an authenticated reverse proxy.

## Runnable routing methods

| API model / route ID | Method | Behavior |
| --- | --- | --- |
| `direct` | Passthrough | Always selects the general model; no judge call. |
| `weighted-random` | Random | Samples general/reasoning models with weights 70%/30%; ignores prompt content. |
| `system-one` | Decision-model classifier | Uses `parallel/decisions-fast:free` through the System One protocol; selects reasoning when specialist advantage exceeds 0.5. |
| `llm-classifier` | Generative LLM classifier | Uses `liquid/lfm-2.5-2.6b:free` over Chat Completions; parses a JSON capability verdict and applies boundary-adjusted thresholds. |

General completion model: `liquid/lfm-3-1.7b:free`.
Reasoning completion model: `nvidia/nemotron-3-ultra-550b-a55b:free`.

The old `auto`, `coding`, `auto-llm`, and `coding-llm` route IDs have been replaced
by the method-specific IDs above. Coding prompts remain possible; they no longer
select a separate task-category route.

In the frontend, select a routing method or use **Compare all methods**. Comparison
sends seven independent requests with the same prompt. Prompt examples never
change the selected method. The route explorer explains the seven configured
methods and separately describes Plan/Execute, Escalation, Stage Router,
Composite, and experimental Prefill routing. Those advanced methods
are **not configured** and have no runnable demo controls.

## Additional runnable methods

| API route ID | Method | What to try |
| --- | --- | --- |
| `custom-selector` | Custom JSON selector | Route among general, reasoning and coding groups. Native custom mode validates the JSON schema and reads `/decision/target`; invalid labels use the general group. |
| `session-pinned` | Session affinity | Submit different tasks using one session ID, then start a new session. The first classifier decision is reused for the original session. |
| `advisor-review` | Advisor gate | The general executor drafts an answer, then the advisor returns APPROVE or REDO. REDO invokes the executor again with correction feedback. The advisor never serves the answer. |

The custom selector adds `cohere/north-mini-code:free` as a third completion
candidate. All three added methods use the same free Liquid LLM judge as the
existing capability classifier. Native custom mode requires JSON Schema support;
provider failures stop the request. Advisor has one review budget per session.
Unparseable advisor verdicts can pass the executor reply under native behavior;
a returned executor answer alone does not prove a valid APPROVE review.

The frontend now exposes **seven** runnable methods. **Compare all methods** sends
seven requests and can consume more free-provider quota than one request.

## Sessions and preview semantics

The frontend generates a session ID and passes it to Switchyard in
`x-switchyard-session-id`. Reuse it to demonstrate pinned selection. **New
session** resets the ID and gives advisor review a fresh session budget.
Changing the prompt does not itself reset a pinned route. State is held in
Switchyard memory and disappears on restart; the frontend session field is
reset when its page reloads. Each API request without an ID receives a new ID.

Advisor selection runs executor/reviewer work during routing, so its **preview
can generate an answer**. The UI explicitly labels this behavior. Buffered
answers are available under `response` in the raw decision response. Other
configured methods preview without a final completion call, though classifiers
still invoke their judge. The native API does not expose APPROVE/REDO details
or raw classifier verdicts per request; these are not invented by the UI.

## Inspect decisions

Each result shows the method, selected target, model pool, configured policy,
judge model when used, actual selection source, latency, response and token usage.
Use **Preview route only** to inspect selection before a completion call:

```bash
curl --fail-with-body http://localhost:4002/v1/decision \
  -H 'Content-Type: application/json' \
  --data '{"input_format":"openai_chat","request":{"model":"weighted-random","messages":[{"role":"user","content":"Explain model routing."}]}}'
```

Direct/random previews select locally. Classifier previews still call their
provider. Random weights are long-run sampling probabilities, not a guaranteed
split across a handful of requests. The native API does not expose judge scores,
raw verdicts or rationales; the frontend does not invent them. The two classifiers
use different score meanings: specialist advantage versus general-model solve
probability. A selected specialist alone does not distinguish a valid judge
verdict from native invalid-verdict fallback.

## Configuration and operations

Edit `routes.toml`, then restart the gateway to apply route changes. Reload the
frontend to refresh its read-only configuration view. Provider-qualified IDs here
are plain OpenRouter IDs, without LiteLLM's `openrouter/` prefix.

```bash
docker compose restart switchyard
# Recreate services after .env changes:
docker compose up -d --force-recreate
# Rebuild after frontend source changes:
docker compose up -d --build --no-deps frontend
# Health and logs:
curl --fail-with-body http://localhost:4002/health
docker compose ps
docker compose logs --tail=100 switchyard
# Stop:
docker compose down
```

Judge timeout is 30 seconds; completion timeout is 120 seconds. `fail_open=false`
propagates judge request failures. Invalid verdicts can still select the
specialist under the native fallback policy. Free endpoints have quotas and
variable availability; no paid targets are configured. Output token limits may
include reasoning, so increase the limit if the answer is empty and finish
reason is `length`.

No database or Redis is required. Session state is in memory and is lost on
restart. The gateway and UI run as non-root users with read-only filesystems.
Logs rotate at 10 MB with three retained files. The Linux native wheel requires
an AVX2-class x86_64 CPU or a Neoverse N1-class aarch64 CPU.

## Verification

Native routing tests use mock endpoints with external networking disabled:

```bash
docker run --rm --network none \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  --entrypoint python model-gateway-switchyard:0.4.0a1 /tests/smoke.py
python3 -m unittest discover -s frontend/tests -p 'test_*.py'
```

See [frontend documentation](frontend/README.md) for browser tests and development.
The [pinned schema](../switchyard/docs/reference/toml_schema.md) documents the
native routing algorithms. Free model availability can change independently of
this configuration.
