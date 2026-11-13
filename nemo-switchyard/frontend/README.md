# APJ AI Innovation Hub — AI Routing Playground

A Dell-inspired blue-and-white frontend branded **APJ AI Innovation Hub** for the standalone Switchyard gateway. It includes prompt
examples, response generation, decision-only previews, side-by-side route
comparisons, a read-only route explorer and in-memory request history.

## Open the application

The frontend is part of the parent Docker Compose stack:

```bash
cd /home/ubuntu/code/model-gateway-router-ws/nemo-switchyard
docker compose up -d --build --wait
```

Open **http://localhost:3002**. Set `FRONTEND_PORT` in the parent `.env` to change
that port. OpenRouter credentials remain on the Switchyard service; the frontend
service and browser receive no provider keys.

For a remote server, forward the frontend port:

```bash
ssh -L 3002:127.0.0.1:3002 ubuntu@EM-MY-2
```

Then open http://localhost:3002 on your computer. The frontend and gateway bind to `0.0.0.0` on the host. Other VMs can open
`http://<host-ip>:3002` directly when network/firewall rules permit. The demo has no user authentication; add authentication and TLS
before exposing either service to other users.

## Explore routing methods

Choose **Direct**, **Weighted random**, **System One**, **LLM classifier**,
**Custom selector**, **Session-pinned**, or **Advisor review**.
The gallery explains what each method does before you send a request. The
frontend focuses on native routing policies rather than auto/coding categories.

1. Select a method and enter a prompt, or use a prompt example.
2. Generate an answer or preview selection only.
3. Use **Compare all methods** to run the same prompt through all seven methods.
4. Inspect the routing-decision card: selected target, candidates, judge when
   applicable, configured policy and actual selection source.

Comparison sends seven independent requests. Direct/random previews do not call
a judge. System One and LLM-classifier previews call their configured provider.
The model pool is the same general/reasoning pair, except the direct baseline
always uses the general model. Prompt examples do not change the method.

The route explorer lists seven runnable configurations and five informational
advanced methods. Plan/Execute, Escalation, Stage Router, Composite and
Prefill are marked **Not configured**. Their additional workflow/model needs
are described; no synthetic results are presented as native execution.

History keeps up to 50 results in page memory and is cleared on reload. Provider
keys are never sent to the browser. The native HTTP API reports selection but
not raw judge scores or rationale. Configured policies are displayed separately
from reported outcomes. Random weights are probabilities, not guaranteed counts.
Free endpoint quotas apply; output budgets may include model reasoning tokens.

## Implementation

- `static/`: responsive HTML, CSS and browser JavaScript; no build tool required.
- `server.py`: Python 3.11+ standard-library server and fixed-upstream API proxy.
- `/api/config`: selected non-secret fields from the mounted `routes.toml`.
- `/api/health` and `/api/models`: gateway health/model discovery.
- `/api/run`: validates a prompt/route, then forwards a chat completion or native
  `/v1/decision` request to Switchyard.

The API upstream is configured server-side with `SWITCHYARD_URL`. Browser input
cannot select another upstream. The proxy forwards neither browser authorization
headers nor provider credentials. It preserves upstream errors and reads the
actual `x-model-router-selected-model` header for completion selection.

The route explorer reads the shared config file. After changing `routes.toml`,
restart Switchyard so its active runtime agrees with the file. Reload the UI to
refresh the configuration display.

For local development without Docker (use an unoccupied port):

```bash
cd frontend
SWITCHYARD_URL=http://127.0.0.1:4002 PORT=3003 python3 server.py
```

After editing frontend source, rebuild only that service:

```bash
docker compose up -d --build --no-deps frontend
```

## Verification

Offline proxy tests need only Python:

```bash
python3 -m unittest discover -s frontend/tests -p 'test_*.py' -v
```

Browser tests use Playwright and intercept every inference request. They verify
examples, generation, preview, comparison, error recovery, history, route
exploration, modal controls and mobile overflow without calling OpenRouter:

```bash
docker build -t switchyard-ui-browser-qa frontend/tests
docker run --rm --network model-gateway-switchyard_default \
  switchyard-ui-browser-qa
```

The running deployment was also checked with a live routed completion. This
verifies connectivity, not classifier accuracy on other tasks.

## Session and advisor demonstrations

Use the session ID field to reuse a native session. **New session** generates a
new identifier. Session-pinned routing reuses its first target for that ID;
changing the prompt does not reclassify it. Session state is server memory,
not browser history. An advisor gets one review budget per session.

**Advisor review preview is not inference-free**: routing itself runs the
executor and may review/revise its answer. The UI marks this and includes the
buffered native response in raw output when available. Custom-selector routing
chooses among three model groups and uses JSON Schema output, while the binary
LLM classifier uses a capability verdict. Provider errors and invalid verdicts
follow Switchyard's native policies rather than a synthetic UI decision.
