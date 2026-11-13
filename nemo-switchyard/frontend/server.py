"""Same-origin UI and a fixed-upstream proxy. No provider credentials are needed."""
import json
import re
import uuid
import os
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import time
import tomllib
import urllib.error
import urllib.request
from urllib.parse import urlsplit

STATIC = Path(__file__).resolve().parent / "static"
CONFIG = Path(os.getenv("ROUTES_CONFIG", str(Path(__file__).resolve().parent.parent / "routes.toml")))
UPSTREAM = os.getenv("SWITCHYARD_URL", "http://127.0.0.1:4002").rstrip("/")


def route_config():
    config = tomllib.loads(CONFIG.read_text())
    targets = config.get("targets", {})
    judges = config.get("decision_targets", {})
    result = []
    for name, route in config.get("routes", {}).items():
        kind = route.get("type")
        def target(name):
            return {"name": name, "model": targets.get(name, {}).get("id", name)}
        if kind == "passthrough":
            method, label = "direct", "Direct"
            candidates = [target(route["target"])]
            description = "Always use one configured model. No classifier and no content-based selection."
            policy = "Always select " + candidates[0]["model"]
        elif kind == "random":
            method, label = "random", "Weighted random"
            candidates = [target(name) for name in route["targets"]]
            weights = route.get("weights", [1] * len(candidates))
            total = sum(weights)
            policy = "; ".join(f"{item['name']}: {weight / total:.0%}" for item, weight in zip(candidates, weights))
            description = "Sample a model using configured weights. Selection does not depend on prompt content."
        elif kind == "advisor":
            method, label = "advisor", "Advisor review"
            candidates = [target(route["executor_target"])]
            description = "Generate on an executor, then ask an advisor to approve or request a corrected answer."
            policy = "Executor serves answers; one APPROVE/REDO review per session. Advisor is not a completion destination."
        elif route.get("mode") == "custom":
            method, label = "custom", "Custom selector"
            candidates = [target(name) for name in route["models"]["any"]]
            description = "A JSON target-selector policy chooses among general, reasoning and coding groups."
            policy = "Read /decision/target from the judge verdict; use the first model in that group. Invalid labels fall back to general."
        else:
            is_decision = "decision" in route
            method = "system_one" if is_decision else "llm"
            label = "System One" if is_decision else "LLM classifier"
            candidates = [target(route["weak_target"]), target(route["strong_target"])]
            description = "A typed decision model estimates specialist advantage before model selection." if is_decision else "A generative LLM returns a JSON capability verdict before model selection."
            policy = "Specialist when advantage > " + str(route["decision"]["cutoff"]) if is_decision else "General when p_solve >= boundary threshold: 0.5 supported, 0.6 uncertain/unmatched, 0.7 unsupported"
            if route.get("classify_trigger") == "new_session":
                method, label = "session", "Session-pinned"
                description = "Classify the first request, then reuse that model for subsequent requests with the same session ID."
                policy = "Native new_session affinity: reuse the first selection until the session changes or server restarts."
        classifier = route.get("classifier_target", route.get("advisor_target", ""))
        if route.get("mode") == "custom":
            classifier = route["models"]["judge"][0]
        judge = judges.get(classifier, targets.get(classifier, {})).get("id", "")
        general = candidates[0]
        specialist = candidates[1] if len(candidates) > 1 else None
        result.append({"id": route.get("id", name), "routing_type": method,
                       "classifier_type": method, "classifier_label": label, "label": label,
                       "general": general, "specialist": specialist, "candidates": candidates,
                       "judge": judge, "policy": policy, "description": description,
                       "preview_runs_completion": method == "advisor", "session_affinity": method == "session"})
    order = {"direct": 0, "random": 1, "system_one": 2, "llm": 3, "custom": 4, "session": 5, "advisor": 6}
    result.sort(key=lambda item: order.get(item["routing_type"], 99))
    return {"routes": result, "gateway": "NeMo Switchyard", "version": "0.4.0a1",
            "advanced_methods": [
                {"label": "Plan / Execute", "description": "Plan on a capable model, then hand off after a recognized edit or write tool call."},
                {"label": "Escalation", "description": "Answer on an efficient model, judge the result, and escalate based on the verdict and session policy."},
                {"label": "Stage router", "description": "Select models by workflow stage and configured handoff rules."},
                {"label": "Composite", "description": "Combine classifier and workflow-stage decisions in one route."},
                {"label": "Prefill router", "description": "Use an experimental checkpoint-based classifier; requires separate model assets and build features."}]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        # Log method/path only, never prompt bodies or provider credentials.
        super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def upstream(self, path, payload=None, timeout=180, route=None, session_id=None):
        started = time.monotonic()
        request = urllib.request.Request(UPSTREAM + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", **({"x-switchyard-session-id": session_id} if session_id else {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.load(response)
                selected = response.headers.get("x-model-router-selected-model") or data.get("selected", {}).get("model") or data.get("model")
                decision = None
                if route:
                    tier = "general" if selected == route["general"]["model"] else "specialist" if route["specialist"] and selected == route["specialist"]["model"] else "other"
                    decision = {"route": route["id"], "classifier_type": route["classifier_type"],
                                "classifier_label": route["classifier_label"], "judge": route["judge"],
                                "selected_model": selected, "selected_tier": tier,
                                "candidates": route["candidates"], "routing_type": route["routing_type"],
                                "selected_label": "Executor" if route["routing_type"] == "advisor" else "Group target" if route["routing_type"] == "custom" else "Configured target" if route["routing_type"] == "direct" else "Pool target" if route["routing_type"] == "random" else "General purpose" if tier == "general" else "Specialist" if tier == "specialist" else "Reported target",
                                "configured_policy": route["policy"], "session_id": session_id,
                                "preview_runs_completion": route["preview_runs_completion"],
                                "fallbacks": data.get("fallbacks") if path == "/v1/decision" else None,
                                "score": None, "rationale": None,
                                "source": "Switchyard decision endpoint" if path == "/v1/decision" else "Switchyard selected-model header / completion response"}
                return self.reply(200, {"data": data, "selected_model": selected, "routing_decision": decision,
                    "latency_ms": round((time.monotonic() - started) * 1000)})
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read())
            except (ValueError, OSError):
                data = {"error": {"message": "Gateway returned an upstream error"}}
            return self.reply(error.code, {"error": data.get("error", data), "status": error.code})
        except (OSError, ValueError, urllib.error.URLError):
            return self.reply(502, {"error": {"message": "Cannot reach Switchyard. Check that the gateway is running and its provider is available."}})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/config":
            try:
                return self.reply(200, route_config())
            except (OSError, ValueError):
                return self.reply(500, {"error": {"message": "Cannot read the mounted routes.toml configuration"}})
        if path == "/api/health":
            return self.upstream("/health", timeout=5)
        if path == "/api/models":
            return self.upstream("/v1/models", timeout=5)
        if path.startswith("/api/"):
            return self.reply(404, {"error": {"message": "Unknown API path"}})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/run":
            return self.reply(404, {"error": {"message": "Unknown API path"}})
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self.reply(403, {"error": {"message": "Use this app from its own origin"}})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Request must be between 1 byte and 64 KB")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Request must be an object")
            prompt = body.get("prompt", "")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000:
                raise ValueError("Enter a prompt of 1 to 16,000 characters")
            route = body.get("route")
            route_meta = next((item for item in route_config()["routes"] if item["id"] == route), None)
            if route_meta is None:
                raise ValueError("Choose a configured route")
            session_id = body.get("session_id") or str(uuid.uuid4())
            if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", session_id):
                raise ValueError("Session ID must be 1–100 letters, digits, or . _ : -")
            mode = body.get("mode", "completion")
            if mode not in {"completion", "preview"}:
                raise ValueError("Choose completion or preview mode")
            tokens = body.get("max_tokens", 512)
            if type(tokens) is not int or not 64 <= tokens <= 4096:
                raise ValueError("Output token limit must be 64 to 4096")
        except (ValueError, TypeError, OSError) as error:
            return self.reply(400, {"error": {"message": str(error)}})
        request = {"model": route, "messages": [{"role": "user", "content": prompt}], "max_tokens": tokens, "stream": False}
        if mode == "preview":
            return self.upstream("/v1/decision", {"input_format": "openai_chat", "request": request}, route=route_meta, session_id=session_id)
        return self.upstream("/v1/chat/completions", request, route=route_meta, session_id=session_id)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Handler)
    print("Switchyard playground listening on :8080", flush=True)
    server.serve_forever()
