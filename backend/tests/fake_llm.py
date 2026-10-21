"""Local stand-ins for the model providers (all four speak the same protocol)."""

import inspect
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLM:
    """A tiny HTTP server. ``handler(method, path, body) -> (status, json)``.
    Every request is recorded in ``requests`` for assertions."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                outer.requests.append(
                    {
                        "method": method,
                        "path": self.path,
                        "body": body,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                    }
                )
                headers = {k.lower(): v for k, v in self.headers.items()}
                if len(inspect.signature(outer.handler).parameters) >= 4:
                    status, payload = outer.handler(method, self.path, body, headers)
                else:
                    status, payload = outer.handler(method, self.path, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):  # noqa: N802
                self._serve("POST")

            def do_GET(self):  # noqa: N802
                self._serve("GET")

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    @property
    def completions(self) -> list[dict]:
        return [r for r in self.requests if r["path"].endswith("/chat/completions")]

    def __enter__(self) -> "FakeLLM":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()


def completion(text="pong", *, finish="stop", model="fake-model", reasoning_tokens=0) -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


def ok_handler(text="pong", models=("fake-model",)):
    def handler(method, path, body):
        if path.endswith("/models"):
            return 200, {"data": [{"id": m} for m in models]}
        return 200, completion(text, model=body["model"])

    return handler


def reasoning_model(threshold=600, text="The agent makes at most two retrieval attempts.", model="nvidia/nemotron-3.5-lightning:free"):
    """Imitates a reasoning model: it thinks first, and if the token budget is below
    ``threshold`` the thinking eats all of it and the answer comes back empty.
    Turning reasoning off ("none") skips the thinking."""

    def handler(method, path, body):
        if path.endswith("/models"):
            return 200, {"data": [{"id": model}]}
        reasoning_off = (body.get("reasoning") or {}).get("effort") == "none" or body.get(
            "reasoning_effort"
        ) == "none"
        if reasoning_off:
            return 200, completion(text, model=model)
        if body["max_tokens"] < threshold:
            return 200, completion("", finish="length", model=model, reasoning_tokens=body["max_tokens"])
        return 200, completion(text, model=model, reasoning_tokens=threshold - 100)

    return handler


def failing(status: int, message: str = "boom"):
    return lambda method, path, body: (status, {"error": {"message": message}})


def gemini_native(*, key, model="gemini-2.5-flash", text="The agent makes at most two retrieval attempts.", threshold=600, models=None):
    """Imitates Google's own generateContent API, including its habits: a wrong key is
    HTTP 400 "API key not valid", and a thinking model whose budget is too small
    returns a candidate with no text and finishReason MAX_TOKENS."""

    def handler(method, path, body, headers):
        if headers.get("x-goog-api-key") != key:
            return 400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
        route = path.split("?")[0]
        if method == "GET" and route.endswith("/models"):
            return 200, {"models": [{"name": f"models/{m}"} for m in (models or [model])]}
        if not route.endswith(f"/models/{model}:generateContent"):
            return 404, {"error": {"code": 404, "message": "models/x is not found for API version v1beta, or is not supported for generateContent.", "status": "NOT_FOUND"}}
        config = body["generationConfig"]
        thinking_off = (config.get("thinkingConfig") or {}).get("thinkingBudget") == 0
        if not thinking_off and config["maxOutputTokens"] < threshold:
            return 200, {
                "candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS", "index": 0}],
                "usageMetadata": {"promptTokenCount": 10, "totalTokenCount": 10 + config["maxOutputTokens"], "thoughtsTokenCount": config["maxOutputTokens"]},
                "modelVersion": model,
            }
        return 200, {
            "candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP", "index": 0}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 8, "totalTokenCount": 118, "thoughtsTokenCount": 0 if thinking_off else threshold - 100},
            "modelVersion": model,
        }

    return handler
