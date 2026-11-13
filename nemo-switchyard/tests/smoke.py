"""Exercise native System One selection and error handling without the network."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

from switchyard_rust.server import Server

os.environ["OPENROUTER_API_KEY"] = "offline-test-key"
probability = 0.1
judge_failure = False
calls = []
custom_group = "coding"
advisor_redo = False


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        calls.append((self.path, payload))
        if self.path == "/decisions":
            assert payload["model"] == "parallel/decisions-fast:free"
            question = payload["questions"]["route"]
            assert question["type"] == "choice"
            assert set(question["criteria"]) == {"advantage", "no_advantage"}
            if judge_failure:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"test decision failure"}}')
                return
            body = {"model": payload["model"], "answers": {"route": {
                "type": "choice",
                "choice": "advantage" if probability > 0.5 else "no_advantage",
                "probabilities": {"advantage": probability, "no_advantage": 1 - probability},
            }}}
        else:
            assert self.path == "/v1/chat/completions", self.path
            assert payload["model"].endswith(":free")
            verdict = {"crux": "bounded task", "primary_rule": "SUP-1", "capability_boundary": "supported", "p_solve": probability}
            content = "Offline reply"
            if payload["model"] == "liquid/lfm-2.5-2.6b:free":
                schema = payload.get("response_format", {}).get("json_schema", {}).get("schema", {})
                if "decision" in schema.get("properties", {}):
                    content = json.dumps({"decision": {"target": custom_group}})
                elif "response_format" not in payload:
                    content = "REDO Fix the answer." if advisor_redo else "APPROVE"
                else:
                    content = json.dumps(verdict)
            body = {"id": "chatcmpl-offline", "object": "chat.completion", "created": 0,
                    "model": payload["model"], "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def request(base_url, route, session=None):
    data = json.dumps({"model": route, "messages": [{"role": "user", "content": "Test request"}]}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json", "x-switchyard-session-id": session or str(uuid.uuid4())})
    return urllib.request.urlopen(req, timeout=15)


upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
thread = threading.Thread(target=upstream.serve_forever, daemon=True)
thread.start()
try:
    origin = f"http://127.0.0.1:{upstream.server_port}"
    config = Path("/app/routes.toml").read_text().replace(
        "https://openrouter.ai/api/v1", origin + "/v1").replace(
        "https://openrouter.ai/api/alpha/decisions", origin + "/decisions")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "routes.toml"
        path.write_text(config)
        with Server(str(path)) as server:
            for route, score, expected in [
                ("direct", 0.1, "liquid/lfm-3-1.7b:free"),
                ("weighted-random", 0.1, None),
                ("system-one", 0.1, "liquid/lfm-3-1.7b:free"),
                ("system-one", 0.5, "liquid/lfm-3-1.7b:free"),
                ("system-one", 0.9, "nvidia/nemotron-3-ultra-550b-a55b:free"),
                ("llm-classifier", 0.9, "liquid/lfm-3-1.7b:free"),
                ("llm-classifier", 0.5, "liquid/lfm-3-1.7b:free"),
                ("llm-classifier", 0.1, "nvidia/nemotron-3-ultra-550b-a55b:free"),
            ]:
                probability = score
                calls.clear()
                with request(server.base_url, route) as response:
                    assert json.load(response)["choices"][0]["message"]["content"] == "Offline reply"
                completion_calls = [p for url, p in calls if url == "/v1/chat/completions" and p["model"] != "liquid/lfm-2.5-2.6b:free"]
                assert len(completion_calls) == 1, calls
                if expected is None:
                    assert completion_calls[0]["model"] in {"liquid/lfm-3-1.7b:free", "nvidia/nemotron-3-ultra-550b-a55b:free"}
                else:
                    assert completion_calls[0]["model"] == expected, calls
                if route == 'llm-classifier':
                    assert len([p for url, p in calls if p.get('model') == 'liquid/lfm-2.5-2.6b:free']) == 1
                elif route == 'system-one':
                    assert len([p for url, p in calls if url == "/decisions"]) == 1
                else:
                    assert len(calls) == 1, calls
                print(f"PASS {route}, advantage={score} -> {expected}")
            # Custom routing supports three destinations; invalid labels use general.
            for group, expected_model in (("coding", "cohere/north-mini-code:free"), ("reasoning", "nvidia/nemotron-3-ultra-550b-a55b:free"), ("not-a-group", "liquid/lfm-3-1.7b:free")):
                custom_group = group; calls.clear()
                with request(server.base_url, "custom-selector") as response: json.load(response)
                served = [body["model"] for url, body in calls if body.get("model") != "liquid/lfm-2.5-2.6b:free"]
                assert served == [expected_model], calls
            print("PASS three-target custom policy and invalid-label default")
            probability = 0.9; pinned_session = str(uuid.uuid4()); calls.clear()
            with request(server.base_url, "session-pinned", pinned_session) as response: json.load(response)
            assert any(body.get("model") == "liquid/lfm-2.5-2.6b:free" for _, body in calls)
            probability = 0.1; calls.clear()
            with request(server.base_url, "session-pinned", pinned_session) as response: json.load(response)
            assert len(calls) == 1 and calls[0][1]["model"] == "liquid/lfm-3-1.7b:free", calls
            calls.clear()
            with request(server.base_url, "session-pinned", str(uuid.uuid4())) as response: json.load(response)
            assert any(body.get("model") == "liquid/lfm-2.5-2.6b:free" for _, body in calls)
            print("PASS session affinity skips judge on reuse and reclassifies a new session")
            for redo in (False, True):
                advisor_redo = redo; calls.clear()
                with request(server.base_url, "advisor-review") as response: json.load(response)
                executors = [body for _, body in calls if body.get("model") == "liquid/lfm-3-1.7b:free"]
                reviews = [body for _, body in calls if body.get("model") == "liquid/lfm-2.5-2.6b:free"]
                assert len(reviews) == 1 and len(executors) == (2 if redo else 1), calls
            print("PASS advisor APPROVE releases executor and REDO invokes correction")
            judge_failure = True
            calls.clear()
            try:
                request(server.base_url, "system-one")
                raise AssertionError("Decision error must not be swallowed")
            except urllib.error.HTTPError as exc:
                assert exc.code >= 400
            assert all(url != "/v1/chat/completions" for url, _ in calls)
            print("PASS decision failure stops completion dispatch")
finally:
    upstream.shutdown()
    upstream.server_close()
print("All offline routing checks passed")

# Exercise the container launcher and TCP forwarding, not only the library API.
launcher = subprocess.Popen([sys.executable, "/app/serve.py"])
try:
    deadline = time.monotonic() + 15
    while True:
        if launcher.poll() is not None:
            raise AssertionError("Container launcher exited before becoming healthy")
        try:
            with urllib.request.urlopen("http://127.0.0.1:4000/health", timeout=1) as response:
                assert response.status == 200
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    with urllib.request.urlopen("http://127.0.0.1:4000/v1/models", timeout=5) as response:
        models = {model["id"] for model in json.load(response)["data"]}
        assert {"direct", "weighted-random", "system-one", "llm-classifier", "custom-selector", "session-pinned", "advisor-review"} <= models, models
    print("PASS container launcher, health endpoint and model discovery")
finally:
    launcher.terminate()
    launcher.wait(timeout=10)
assert launcher.returncode == 0, launcher.returncode
print("PASS graceful container shutdown")
