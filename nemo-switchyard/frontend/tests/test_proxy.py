"""Offline contract tests for the browser-to-Switchyard proxy."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location("frontend", Path(__file__).resolve().parents[1] / "server.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
requests = []


class MockGateway(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("x-model-router-selected-model", "test/free-model:free")
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self): self.send({"status": "ok"})
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append((self.path, data))
        self.send({"model": "test/free-model:free", "choices": [{"message": {"content": "Offline answer"}}]})


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = ThreadingHTTPServer(("127.0.0.1", 0), MockGateway)
        app.UPSTREAM = f"http://127.0.0.1:{cls.gateway.server_port}"
        cls.frontend = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        for server in (cls.gateway, cls.frontend):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.frontend.server_port}"
    @classmethod
    def tearDownClass(cls):
        for server in (cls.frontend, cls.gateway): server.shutdown(); server.server_close()
    def post(self, body, headers=None):
        req = urllib.request.Request(self.url + "/api/run", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **(headers or {})})
        return urllib.request.urlopen(req)
    def test_completion_uses_fixed_upstream_and_reports_actual_header(self):
        with self.post({"route": "system-one", "prompt": "Hello", "max_tokens": 512}) as response:
            body = json.load(response)
        self.assertEqual(body["selected_model"], "test/free-model:free")
        self.assertEqual(body["routing_decision"]["classifier_type"], "system_one")
        self.assertIsNone(body["routing_decision"]["score"])
        self.assertEqual(requests[-1][0], "/v1/chat/completions")
        self.assertEqual(requests[-1][1]["messages"][0]["content"], "Hello")
        self.assertGreaterEqual(body["latency_ms"], 0)
    def test_preview_wraps_native_decision_request(self):
        with self.post({"route": "weighted-random", "prompt": "Write code", "mode": "preview"}): pass
        self.assertEqual(requests[-1][0], "/v1/decision")
        self.assertEqual(requests[-1][1]["input_format"], "openai_chat")
        self.assertEqual(requests[-1][1]["request"]["model"], "weighted-random")
    def test_llm_route_reports_its_classifier(self):
        with self.post({"route": "llm-classifier", "prompt": "Hello"}) as response:
            decision = json.load(response)["routing_decision"]
        self.assertEqual(decision["classifier_type"], "llm")
        self.assertEqual(decision["judge"], "liquid/lfm-2.5-2.6b:free")
        self.assertEqual(len(decision["candidates"]), 2)

    def test_advisor_preview_and_session_are_reported(self):
        with self.post({"route": "advisor-review", "prompt": "Hello", "mode": "preview", "session_id": "lab-test"}) as response:
            decision = json.load(response)["routing_decision"]
        self.assertTrue(decision["preview_runs_completion"])
        self.assertEqual(decision["session_id"], "lab-test")

    def test_invalid_inputs_never_reach_gateway(self):
        count = len(requests)
        for body in ({"route": "unknown", "prompt": "Hi"}, {"route": "system-one", "prompt": ""},
                     {"route": "system-one", "prompt": "Hi", "max_tokens": 999999},
                     {"route": "system-one", "prompt": "Hi", "mode": "unknown"}):
            with self.assertRaises(urllib.error.HTTPError) as error: self.post(body)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(len(requests), count)
    def test_direct_has_one_destination_and_no_judge(self):
        with self.post({"route": "direct", "prompt": "Hello", "mode": "preview"}) as response:
            decision = json.load(response)["routing_decision"]
        self.assertEqual(decision["judge"], "")
        self.assertEqual(len(decision["candidates"]), 1)
        self.assertEqual(decision["selected_label"], "Configured target")

    def test_cross_origin_posts_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({"route": "system-one", "prompt": "Hi"}, {"Origin": "http://untrusted.example"})
        self.assertEqual(error.exception.code, 403)
    def test_config_has_routes_and_no_credentials(self):
        with urllib.request.urlopen(self.url + "/api/config") as response: data = json.load(response)
        self.assertEqual({r["id"] for r in data["routes"]}, {"direct", "weighted-random", "system-one", "llm-classifier", "custom-selector", "session-pinned", "advisor-review"})
        self.assertNotIn("api_key", json.dumps(data))
    def test_gateway_unavailable_has_actionable_error(self):
        old = app.UPSTREAM
        app.UPSTREAM = "http://127.0.0.1:1"
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(self.url + "/api/health")
            self.assertEqual(error.exception.code, 502)
            self.assertIn("Cannot reach Switchyard", error.exception.read().decode())
        finally: app.UPSTREAM = old


if __name__ == "__main__": unittest.main()
