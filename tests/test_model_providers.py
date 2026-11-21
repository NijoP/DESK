"""Model-agnostic provider layer (desk/orchestrator/providers/).

No network and no keys: HTTP adapters run against a recording transport that replays synthetic
fixtures written in each provider's documented wire format; orchestration logic runs against a
fake in-process provider. Software-tested with fixtures; not validated against live endpoints.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from desk.orchestrator.providers.accounting import UsageLedger
from desk.orchestrator.providers.allocation import POLICY, allocate, independent_verifiers, load_policy
from desk.orchestrator.providers.anthropic import AnthropicProvider, to_anthropic
from desk.orchestrator.providers.base import (ChatRequest, ChatResponse, ModelProvider, ModelRoute, ProviderError,
                                              Transport, Usage, error_for_status, redact, sse_data)
from desk.orchestrator.providers.bridge import ProviderTaskAdapter, adapter_for_model, register_with_router
from desk.orchestrator.providers.catalog import PRESETS, ModelCatalog, ModelDescriptor
from desk.orchestrator.providers.gemini import GeminiProvider
from desk.orchestrator.providers.openai_compat import OpenAICompatProvider
from desk.orchestrator.providers.prompt_tools import parse_reply
from desk.orchestrator.providers.registry import ModelProviderRegistry, credential
from desk.orchestrator.providers.resilience import FallbackExhausted, ResilientClient, RetryPolicy

TOOLS = [{"type": "function", "function": {
    "name": "list_schematic_nets", "description": "READ-ONLY nets",
    "parameters": {"type": "object", "additionalProperties": False,
                   "properties": {"project": {"type": "string"}}, "required": ["project"]}}}]


# ---------------------------------------------------------------------------------------------- doubles
class RecordingTransport(Transport):
    """Replays queued fixtures per URL suffix and records every request."""

    def __init__(self):
        self.queue = {}
        self.requests = []

    def add(self, suffix, *responses):
        self.queue.setdefault(suffix, []).extend(responses)
        return self

    def _next(self, url):
        for suffix, q in self.queue.items():
            if url.endswith(suffix) and q:
                r = q.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r
        raise AssertionError(f"no fixture for {url}")

    def post_json(self, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return self._next(url)

    def get_json(self, url, headers, timeout):
        self.requests.append({"url": url, "headers": headers, "body": None, "timeout": timeout})
        return self._next(url)

    def stream_lines(self, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return iter(self._next(url))


class FakeProvider(ModelProvider):
    """In-process provider: scripted ChatResponses or ProviderErrors, records ChatRequests."""
    kind = "fake"

    def __init__(self, name="fake", script=(), ready=True):
        self.name = name
        self.script = list(script)
        self.requests = []
        self.ready = ready

    def configured(self):
        return (self.ready, "fake ready" if self.ready else "fake has no key")

    def chat(self, req):
        self.requests.append(req)
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, str):
            return ChatResponse(provider=self.name, model=req.model, text=r, usage=Usage(10, 5))
        return r

    def list_models(self, timeout=10.0):
        return ["m1", "m2"]


def registry_with(*fakes, descriptors=()):
    reg = ModelProviderRegistry(transport=RecordingTransport(),
                                catalog=ModelCatalog(entries=list(descriptors), load_operator_file=False),
                                load_operator_file=False)
    for f in fakes:
        reg.register(f)
    return reg


def desc(provider, model, **kw):
    base = dict(context_window=32000, native_tools=True, structured_output=True, streaming=True, source="operator")
    base.update(kw)
    return ModelDescriptor(provider=provider, model=model, **base)


def sse(*objs, done=True):
    lines = []
    for o in objs:
        if isinstance(o, tuple):
            lines += [f"event: {o[0]}", "data: " + json.dumps(o[1]), ""]
        else:
            lines += ["data: " + json.dumps(o), ""]
    if done:
        lines += ["data: [DONE]", ""]
    return lines


# ---------------------------------------------------------------------------------------------- OpenAI-compatible
class OpenAICompatTests(unittest.TestCase):
    def provider(self, name="nvidia", key="nvapi-test-0000000000", t=None):
        p = PRESETS[name]
        return OpenAICompatProvider(name, p.base_url, api_key=key, key_setting=p.key_setting,
                                    transport=t or RecordingTransport(), thinking_style=p.thinking_style, local=p.local)

    def test_nim_thinking_off_and_openai_has_no_nim_fields(self):
        req = ChatRequest(model="m", messages=[{"role": "user", "content": "hi"}], tools=TOOLS, thinking="off", json_mode=True)
        nim = self.provider("nvidia").build_body(req)
        self.assertEqual(nim["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(nim["response_format"], {"type": "json_object"})
        oai = self.provider("openai", key="sk-test").build_body(req)
        self.assertNotIn("chat_template_kwargs", oai)
        self.assertNotIn("reasoning_effort", oai)
        req.thinking = "high"
        self.assertEqual(self.provider("openai", key="sk-test").build_body(req)["reasoning_effort"], "high")

    def test_tool_call_response_and_provider_meta_stripped(self):
        t = RecordingTransport().add("/chat/completions", {"model": "m", "choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "list_schematic_nets", "arguments": "{\"project\": \"p\"}"}}]}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 7}})
        msgs = [{"role": "assistant", "content": "", "tool_calls": [{"id": "x", "type": "function", "provider_meta": {"a": 1},
                                                                     "function": {"name": "n", "arguments": "{}"}}]}]
        r = self.provider(t=t).chat(ChatRequest(model="m", messages=msgs, tools=TOOLS))
        self.assertEqual(r.tool_calls[0].name, "list_schematic_nets")
        self.assertEqual(r.tool_calls[0].arguments, {"project": "p"})
        self.assertEqual((r.usage.input_tokens, r.usage.output_tokens), (40, 7))
        sent = t.requests[0]
        self.assertNotIn("provider_meta", sent["body"]["messages"][0]["tool_calls"][0])
        self.assertEqual(sent["headers"]["Authorization"], "Bearer nvapi-test-0000000000")
        self.assertTrue(sent["url"].startswith("https://integrate.api.nvidia.com/v1"))

    def test_stream_assembles_text_and_split_tool_arguments(self):
        t = RecordingTransport().add("/chat/completions", sse(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c9", "function": {"name": "doctor", "arguments": "{\"pro"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ject\": \"p\"}"}}]},
                          "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 4}}))
        events = list(self.provider(t=t).stream(ChatRequest(model="m", messages=[{"role": "user", "content": "x"}])))
        self.assertEqual([e.text for e in events if e.type == "text"], ["Hel", "lo"])
        done = events[-1].response
        self.assertEqual(done.text, "Hello")
        self.assertEqual(done.tool_calls[0].arguments, {"project": "p"})
        self.assertEqual(done.finish_reason, "tool_calls")
        self.assertEqual(done.usage.total_tokens, 7)
        self.assertTrue(t.requests[0]["body"]["stream"])

    def test_models_listing_and_local_preset_sends_no_auth(self):
        t = RecordingTransport().add("/models", {"data": [{"id": "qwen3:8b"}, {"id": "llama3.2:3b"}]})
        p = self.provider("ollama", key=None, t=t)
        self.assertTrue(p.configured()[0])
        self.assertEqual(p.list_models(), ["qwen3:8b", "llama3.2:3b"])
        self.assertNotIn("Authorization", t.requests[0]["headers"])
        self.assertTrue(t.requests[0]["url"].startswith("http://127.0.0.1:11434/v1"))

    def test_missing_key_is_a_config_error_not_a_request(self):
        t = RecordingTransport()
        p = self.provider("openai", key=None, t=t)
        self.assertFalse(p.configured()[0])
        with self.assertRaises(ProviderError) as cm:
            p.chat(ChatRequest(model="m", messages=[]))
        self.assertEqual(cm.exception.kind, "config")
        self.assertEqual(t.requests, [])

    def test_malformed_response(self):
        t = RecordingTransport().add("/chat/completions", {"oops": 1})
        with self.assertRaises(ProviderError) as cm:
            self.provider(t=t).chat(ChatRequest(model="m", messages=[]))
        self.assertEqual(cm.exception.kind, "bad_response")


# ---------------------------------------------------------------------------------------------- Anthropic
CONVO = [
    {"role": "system", "content": "You are DESK."},
    {"role": "user", "content": "list nets"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "tu_1", "type": "function", "function": {"name": "list_schematic_nets", "arguments": "{\"project\": \"p\"}"}},
        {"id": "tu_2", "type": "function", "function": {"name": "doctor", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "tu_1", "name": "list_schematic_nets", "content": "{\"nets\": {}}"},
    {"role": "tool", "tool_call_id": "tu_2", "name": "doctor", "content": "{\"checks\": []}"},
    {"role": "user", "content": "continue"},
]


class AnthropicTests(unittest.TestCase):
    def test_conversion_merges_tool_results_into_one_user_turn(self):
        system, turns = to_anthropic(CONVO)
        self.assertEqual(system, "You are DESK.")
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])
        self.assertEqual([b["type"] for b in turns[1]["content"]], ["tool_use", "tool_use"])
        self.assertEqual(turns[1]["content"][0]["input"], {"project": "p"})
        self.assertEqual([b["type"] for b in turns[2]["content"]], ["tool_result", "tool_result", "text"])
        self.assertEqual(turns[2]["content"][0]["tool_use_id"], "tu_1")

    def test_request_and_response(self):
        t = RecordingTransport().add("/messages", {
            "type": "message", "model": "claude-x", "stop_reason": "tool_use",
            "content": [{"type": "text", "text": "Checking."},
                        {"type": "tool_use", "id": "tu_9", "name": "list_schematic_nets", "input": {"project": "p"}}],
            "usage": {"input_tokens": 120, "output_tokens": 30}})
        r = AnthropicProvider(api_key="sk-ant-test-000000", transport=t).chat(
            ChatRequest(model="claude-x", messages=CONVO, tools=TOOLS, json_mode=True))
        body, headers = t.requests[0]["body"], t.requests[0]["headers"]
        self.assertEqual(headers["x-api-key"], "sk-ant-test-000000")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", headers)
        self.assertEqual(body["tools"][0]["input_schema"]["required"], ["project"])
        self.assertEqual(body["tool_choice"], {"type": "auto"})
        self.assertIn("single JSON object", body["system"])
        self.assertEqual((r.text, r.tool_calls[0].id, r.usage.total_tokens), ("Checking.", "tu_9", 150))

    def test_stream_events(self):
        t = RecordingTransport().add("/messages", sse(
            ("message_start", {"type": "message_start", "message": {"model": "claude-x", "usage": {"input_tokens": 11}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hi"}}),
            ("content_block_start", {"type": "content_block_start", "index": 1,
                                     "content_block": {"type": "tool_use", "id": "tu_3", "name": "doctor"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                     "delta": {"type": "input_json_delta", "partial_json": "{\"project\":"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                     "delta": {"type": "input_json_delta", "partial_json": " \"p\"}"}}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 9}}),
            ("message_stop", {"type": "message_stop"}), done=False))
        events = list(AnthropicProvider(api_key="k", transport=t).stream(ChatRequest(model="claude-x", messages=CONVO)))
        done = events[-1].response
        self.assertEqual(done.text, "Hi")
        self.assertEqual(done.tool_calls[0].arguments, {"project": "p"})
        self.assertEqual((done.usage.input_tokens, done.usage.output_tokens, done.finish_reason), (11, 9, "tool_use"))

    def test_overloaded_stream_error_is_retryable(self):
        t = RecordingTransport().add("/messages", sse(("error", {"type": "error", "error": {"type": "overloaded_error",
                                                                                             "message": "busy"}}), done=False))
        with self.assertRaises(ProviderError) as cm:
            list(AnthropicProvider(api_key="k", transport=t).stream(ChatRequest(model="m", messages=CONVO)))
        self.assertTrue(cm.exception.retryable)


# ---------------------------------------------------------------------------------------------- Gemini
class GeminiTests(unittest.TestCase):
    def test_request_shape_and_thought_signature_round_trip(self):
        convo = [dict(m) for m in CONVO]
        convo[2]["tool_calls"] = [dict(CONVO[2]["tool_calls"][0], provider_meta={"thoughtSignature": "sig-abc"})]
        convo = convo[:4] + convo[5:]
        t = RecordingTransport().add(":generateContent", {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]},
                                                                          "finishReason": "STOP"}]})
        GeminiProvider(api_key="AIza-test-000000", transport=t).chat(
            ChatRequest(model="models/gemini-x", messages=convo, tools=TOOLS, json_mode=True))
        req = t.requests[0]
        self.assertTrue(req["url"].endswith("/models/gemini-x:generateContent"))
        self.assertNotIn("key=", req["url"])
        self.assertEqual(req["headers"]["x-goog-api-key"], "AIza-test-000000")
        body = req["body"]
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "You are DESK.")
        self.assertEqual([c["role"] for c in body["contents"]], ["user", "model", "user"])
        fc_part = body["contents"][1]["parts"][0]
        self.assertEqual(fc_part["functionCall"], {"name": "list_schematic_nets", "args": {"project": "p"}})
        self.assertEqual(fc_part["thoughtSignature"], "sig-abc")
        fr = body["contents"][2]["parts"][0]["functionResponse"]
        self.assertEqual((fr["name"], fr["response"]["result"]), ("list_schematic_nets", {"nets": {}}))
        decl = body["tools"][0]["functionDeclarations"][0]
        self.assertNotIn("additionalProperties", decl["parameters"])
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["toolConfig"]["functionCallingConfig"]["mode"], "AUTO")

    def test_function_call_response(self):
        t = RecordingTransport().add(":generateContent", {
            "modelVersion": "gemini-x-001",
            "candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [
                {"text": "internal", "thought": True},
                {"functionCall": {"name": "doctor", "args": {}}, "thoughtSignature": "sig-1"}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 6}})
        r = GeminiProvider(api_key="k", transport=t).chat(ChatRequest(model="gemini-x", messages=CONVO[:2]))
        self.assertEqual(r.text, "")
        self.assertEqual(r.tool_calls[0].id, "gemini_call_1")
        self.assertEqual(r.tool_calls[0].provider_meta, {"thoughtSignature": "sig-1"})
        self.assertEqual((r.usage.input_tokens, r.usage.output_tokens, r.model), (50, 6, "gemini-x-001"))
        self.assertEqual(r.tool_calls[0].to_openai()["provider_meta"]["thoughtSignature"], "sig-1")

    def test_blocked_prompt_and_stream_and_models(self):
        t = RecordingTransport().add(":generateContent", {"promptFeedback": {"blockReason": "SAFETY"}})
        with self.assertRaises(ProviderError):
            GeminiProvider(api_key="k", transport=t).chat(ChatRequest(model="g", messages=CONVO[:2]))
        t.add(":streamGenerateContent?alt=sse", sse(
            {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]},
            {"candidates": [{"content": {"parts": [{"text": "lo"}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 2}}, done=False))
        events = list(GeminiProvider(api_key="k", transport=t).stream(ChatRequest(model="g", messages=CONVO[:2])))
        self.assertEqual(events[-1].response.text, "Hello")
        self.assertEqual(events[-1].response.usage.total_tokens, 4)
        t.add("/models", {"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                                     {"name": "models/embed-y", "supportedGenerationMethods": ["embedContent"]}]})
        self.assertEqual(GeminiProvider(api_key="k", transport=t).list_models(), ["gemini-x"])


# ---------------------------------------------------------------------------------------------- prompt tools
class PromptToolTests(unittest.TestCase):
    def test_parse_reply(self):
        text, calls = parse_reply('```json\n{"tool_calls": [{"name": "doctor", "arguments": "{\\"project\\": \\"p\\"}"}]}\n```')
        self.assertEqual((text, calls[0].name, calls[0].arguments), ("", "doctor", {"project": "p"}))
        text, calls = parse_reply('{"nets_wired": []}')
        self.assertEqual((text, calls), ('{"nets_wired": []}', []))

    def test_model_without_native_tools_gets_protocol_and_text_history(self):
        fake = FakeProvider("local", ['{"tool_calls": [{"name": "list_schematic_nets", "arguments": {"project": "p"}}]}',
                                      "Done: no nets."])
        reg = registry_with(fake, descriptors=[desc("local", "tiny", native_tools=False, structured_output=False)])
        client = ResilientClient(reg, [ModelRoute("local", "tiny")])
        msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "go"}]
        r1 = client.chat(msgs, tools=TOOLS)
        self.assertEqual((r1.via, r1.tool_calls[0].name), ("prompt_tools", "list_schematic_nets"))
        sent = fake.requests[0]
        self.assertIsNone(sent.tools)
        self.assertIn("SYS", sent.messages[0]["content"])
        self.assertIn('"tool_calls"', sent.messages[0]["content"])
        msgs += [r1.message(), {"role": "tool", "tool_call_id": r1.tool_calls[0].id, "name": "list_schematic_nets",
                                "content": "{\"nets\": {}}"}]
        r2 = client.chat(msgs, tools=TOOLS)
        self.assertEqual((r2.text, r2.tool_calls), ("Done: no nets.", []))
        rendered = fake.requests[1].messages
        self.assertEqual(rendered[2]["role"], "assistant")
        self.assertIn("list_schematic_nets", rendered[2]["content"])
        self.assertTrue(rendered[3]["content"].startswith("TOOL_RESULT list_schematic_nets"))
        self.assertNotIn("tool", [m["role"] for m in rendered])


# ---------------------------------------------------------------------------------------------- resilience
class ResilienceTests(unittest.TestCase):
    def client(self, reg, routes, **kw):
        self.sleeps = []
        return ResilientClient(reg, routes, sleep=self.sleeps.append, **kw)

    def test_retry_with_backoff_then_success(self):
        fake = FakeProvider("a", [error_for_status(503, "busy"), ProviderError("timed out", kind="timeout", retryable=True), "ok"])
        c = self.client(registry_with(fake), [ModelRoute("a", "m")], retry=RetryPolicy(max_attempts=3, base_delay_s=0.5))
        self.assertEqual(c.chat([{"role": "user", "content": "x"}]).text, "ok")
        self.assertEqual(self.sleeps, [0.5, 1.0])
        s = c.ledger.summary()
        self.assertEqual((s["calls"], s["failures"]), (3, 2))

    def test_retry_after_is_honoured_but_capped(self):
        fake = FakeProvider("a", [error_for_status(429, "slow down", retry_after=30.0), "ok"])
        c = self.client(registry_with(fake), [ModelRoute("a", "m")], retry=RetryPolicy(max_attempts=2, max_delay_s=8.0))
        c.chat([{"role": "user", "content": "x"}])
        self.assertEqual(self.sleeps, [8.0])

    def test_auth_error_falls_back_without_retry(self):
        a = FakeProvider("a", [error_for_status(401, "bad key sk-abcdefghijklmnop")])
        b = FakeProvider("b", ["from b"])
        c = self.client(registry_with(a, b), [ModelRoute("a", "m"), ModelRoute("b", "m")])
        r = c.chat([{"role": "user", "content": "x"}])
        self.assertEqual((r.text, r.provider), ("from b", "b"))
        self.assertEqual(self.sleeps, [])
        self.assertEqual(len(a.requests), 1)
        self.assertNotIn("abcdefghijklmnop", c.last_reasons[0]["reason"])

    def test_capability_and_configuration_gates_skip_routes(self):
        small, novision = FakeProvider("small", []), FakeProvider("novision", [])
        nokey, good = FakeProvider("nokey", [], ready=False), FakeProvider("good", ["seen"])
        reg = registry_with(small, novision, nokey, good, descriptors=[
            desc("small", "m", context_window=64, vision=True), desc("novision", "m", vision=False),
            desc("nokey", "m", vision=True), desc("good", "m", vision=True)])
        c = self.client(reg, [ModelRoute(n, "m") for n in ("small", "novision", "nokey", "good")])
        r = c.chat([{"role": "user", "content": "x" * 400}], requires_vision=True, max_tokens=32)
        self.assertEqual(r.provider, "good")
        reasons = [x["reason"] for x in c.last_reasons]
        self.assertIn("context window is 64", reasons[0])
        self.assertIn("no vision", reasons[1])
        self.assertIn("no key", reasons[2])
        self.assertEqual((small.requests, novision.requests, nokey.requests), ([], [], []))

    def test_all_routes_fail(self):
        c = self.client(registry_with(FakeProvider("a", [error_for_status(400, "bad")])), [ModelRoute("a", "m")])
        with self.assertRaises(FallbackExhausted) as cm:
            c.chat([{"role": "user", "content": "x"}])
        self.assertEqual(cm.exception.reasons[0]["kind"], "bad_request")

    def test_json_and_thinking_follow_descriptor(self):
        native, prompt = FakeProvider("n", ["{}"]), FakeProvider("p", ["{}"])
        reg = registry_with(native, prompt, descriptors=[desc("n", "m", thinking_controllable=True),
                                                         desc("p", "m", structured_output=False)])
        ResilientClient(reg, [ModelRoute("n", "m")]).chat([{"role": "user", "content": "x"}], json_mode=True, thinking="off")
        ResilientClient(reg, [ModelRoute("p", "m")]).chat([{"role": "user", "content": "x"}], json_mode=True, thinking="off")
        self.assertTrue(native.requests[0].json_mode)
        self.assertEqual(native.requests[0].thinking, "off")
        self.assertFalse(prompt.requests[0].json_mode)
        self.assertIsNone(prompt.requests[0].thinking)
        self.assertIn("single JSON object", prompt.requests[0].messages[0]["content"])

    def test_deadline_stops_retries(self):
        fake = FakeProvider("a", [error_for_status(503, "x")] * 5)
        c = self.client(registry_with(fake), [ModelRoute("a", "m")], retry=RetryPolicy(max_attempts=5))
        clock = iter([0.0, 0.0, 100.0, 100.0, 100.0])
        with mock.patch("desk.orchestrator.providers.resilience.time.monotonic", side_effect=lambda: next(clock)):
            with self.assertRaises(FallbackExhausted) as cm:
                c.chat([{"role": "user", "content": "x"}], deadline_s=10.0)
        self.assertIn("deadline", cm.exception.reasons[-1]["reason"])
        self.assertEqual(len(fake.requests), 1)

    def test_stream_falls_back_only_before_first_event(self):
        t = RecordingTransport()
        t.add("/chat/completions", error_for_status(503, "down"))
        t.add("/messages", sse(("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                        "delta": {"type": "text_delta", "text": "hi"}}), done=False))
        reg = ModelProviderRegistry(transport=t, catalog=ModelCatalog(entries=[], load_operator_file=False),
                                    load_operator_file=False)
        reg.register(OpenAICompatProvider("openai", "https://x/v1", api_key="sk-t", key_setting="OPENAI_API_KEY", transport=t))
        reg.register(AnthropicProvider(api_key="k", transport=t))
        c = ResilientClient(reg, [ModelRoute("openai", "m"), ModelRoute("anthropic", "c")], retry=RetryPolicy(max_attempts=1))
        events = list(c.stream([{"role": "user", "content": "x"}]))
        self.assertEqual(events[-1].response.text, "hi")
        self.assertEqual(events[-1].response.provider, "anthropic")
        self.assertIn("HTTP 503", c.last_reasons[0]["reason"])


# ---------------------------------------------------------------------------------------------- accounting
class AccountingTests(unittest.TestCase):
    def test_cost_only_from_known_prices_and_estimates_flagged(self):
        priced = FakeProvider("priced", ["ok"])
        unpriced = FakeProvider("unpriced", [ChatResponse(provider="unpriced", model="m", text="abcdefgh")])
        reg = registry_with(priced, unpriced, descriptors=[desc("priced", "m", input_per_mtok=2.0, output_per_mtok=10.0)])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state", "model_usage.jsonl")
            ledger = UsageLedger(path)
            ResilientClient(reg, [ModelRoute("priced", "m")], ledger=ledger).chat([{"role": "user", "content": "x"}])
            ResilientClient(reg, [ModelRoute("unpriced", "m")], ledger=ledger).chat([{"role": "user", "content": "x"}])
            with open(path, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f]
        self.assertEqual(rows[0]["cost_usd"], round(10 * 2.0 / 1e6 + 5 * 10.0 / 1e6, 6))
        self.assertIsNone(rows[1]["cost_usd"])
        self.assertTrue(rows[1]["estimated"])
        self.assertEqual(rows[1]["output_tokens"], 3)
        self.assertRegex(rows[0]["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        s = ledger.summary()
        self.assertEqual((s["unpriced_calls"], s["estimated_calls"], s["calls"]), (1, 1, 2))


# ---------------------------------------------------------------------------------------------- catalog / registry
class RegistryTests(unittest.TestCase):
    def test_verified_and_assumed_descriptors(self):
        cat = ModelCatalog(load_operator_file=False)
        ultra = cat.get("nvidia", "nvidia/nemotron-3-ultra-550b-a55b")
        self.assertEqual((ultra.source, ultra.native_tools, ultra.context_window), ("verified", True, 131072))
        local = cat.get("ollama", "whatever:7b")
        self.assertEqual((local.source, local.native_tools, local.input_per_mtok), ("assumed", False, 0.0))
        self.assertIsNone(cat.get("openai", "any").input_per_mtok)

    def test_operator_catalog_file_adds_models_and_providers(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "catalog.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"models": [{"provider": "ollama", "model": "tiny:1b", "context_window": 4096,
                                       "input_per_mtok": 0.5, "output_per_mtok": 1.5}],
                           "providers": [{"name": "lab-vllm", "kind": "openai_compat", "base_url": "http://10.0.0.5:8000/v1",
                                          "key_setting": None}]}, f)
            with mock.patch.dict(os.environ, {"DESK_MODEL_CATALOG_FILE": path}):
                reg = ModelProviderRegistry(transport=RecordingTransport())
        tiny = reg.descriptor(ModelRoute("ollama", "tiny:1b"))
        self.assertEqual((tiny.context_window, tiny.input_per_mtok, tiny.source), (4096, 0.5, "operator"))
        self.assertTrue(reg.has("lab-vllm"))
        self.assertEqual(reg.get("lab-vllm").base_url, "http://10.0.0.5:8000/v1")

    def test_parse_route(self):
        reg = ModelProviderRegistry(transport=RecordingTransport(), load_operator_file=False)
        self.assertEqual(reg.parse_route("ollama:qwen3:8b"), ModelRoute("ollama", "qwen3:8b"))
        self.assertEqual(reg.parse_route("grok:grok-x"), ModelRoute("xai", "grok-x"))
        self.assertEqual(reg.parse_route("qwen3:8b", default_provider="ollama"), ModelRoute("ollama", "qwen3:8b"))
        with self.assertRaises(ProviderError):
            reg.parse_route("nvidia/nemotron-3-ultra-550b-a55b")

    def test_credentials_from_environment_and_base_url_override(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-env-123456",
                                          "DESK_OLLAMA_BASE_URL": "http://gpu-box:11434/v1"}):
            self.assertEqual(credential("openai", "OPENAI_API_KEY")(), "sk-from-env-123456")
            reg = ModelProviderRegistry(transport=RecordingTransport(), load_operator_file=False)
            self.assertTrue(reg.get("openai").configured()[0])
            self.assertEqual(reg.get("ollama").base_url, "http://gpu-box:11434/v1")
        self.assertEqual(redact("HTTP 401 key sk-from-env-123456"), "HTTP 401 key sk-[REDACTED]")
        self.assertIsNone(credential("ollama", None)())

    def test_discovery_skips_unconfigured_and_local(self):
        t = RecordingTransport().add("/models", {"data": [{"id": "a"}]}, error_for_status(500, "x"))
        reg = ModelProviderRegistry(transport=t, load_operator_file=False)
        keys = {"OPENAI_API_KEY": "sk-t", "XAI_API_KEY": "xai-t"}
        with mock.patch("desk.orchestrator.providers.registry.credential", side_effect=lambda p, k: (lambda: keys.get(k))):
            res = reg.discover()
        self.assertEqual(res["openai"], {"ok": True, "models": ["a"]})
        self.assertFalse(res["xai"]["ok"])
        self.assertEqual(res["xai"]["kind"], "server")
        self.assertIn("local server", res["ollama"]["skipped"])
        self.assertIn("no API key", res["anthropic"]["skipped"])
        self.assertEqual(len(t.requests), 2)

    def test_sse_parser(self):
        self.assertEqual(list(sse_data(["event: a", "data: 1", "", ": c", "data: [DONE]", "", "data: 2", ""])), [("a", "1")])


# ---------------------------------------------------------------------------------------------- allocation
class AllocationTests(unittest.TestCase):
    def test_deterministic_first(self):
        for c in ("calculation", "validation", "drc_erc", "repetitive"):
            a = allocate(c, policy=POLICY)
            self.assertTrue(a.deterministic)
            self.assertEqual((a.tier, a.routes), (0, []))

    def test_small_model_for_classification_and_strong_for_power(self):
        cls = allocate("classification", policy=POLICY)
        self.assertEqual((cls.tier, cls.json, cls.verify, cls.thinking), (1, True, False, "off"))
        self.assertEqual(cls.routes, ["nvidia:nvidia/nemotron-3.5-lightning-30b-a3b"])
        pwr = allocate("power_electronics", policy=POLICY)
        self.assertEqual((pwr.tier, pwr.verify), (3, True))
        self.assertNotIn(pwr.routes[0], pwr.verifier_routes)
        self.assertEqual(pwr.verifier_independence, "model")
        self.assertIn("never the sole authority", pwr.authority)

    def test_domain_escalation_and_unknown_class(self):
        a = allocate("extraction", domains=["mains"], policy=POLICY)
        self.assertEqual((a.tier, a.verify, a.escalated_by), (3, True, ["mains"]))
        with self.assertRaises(ValueError):
            allocate("make_it_work", policy=POLICY)

    def test_verifier_prefers_another_provider_and_reports_missing(self):
        routes, level = independent_verifiers("anthropic:a", ["anthropic:a", "anthropic:b", "gemini:g"])
        self.assertEqual((routes, level), (["gemini:g", "anthropic:b"], "provider"))
        pol = load_policy()
        pol["tiers"] = {"3": ["ollama:only"], "verifier": ["ollama:only"]}
        a = allocate("rf", policy=pol)
        self.assertEqual(a.verifier_routes, [])
        self.assertIn("no independent verifier", a.open_issue)

    def test_policy_file_overrides_tiers_but_not_authority(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "policy.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"tiers": {"1": ["ollama:example-small:8b"]}, "authority": "the model decides"}, f)
            pol = load_policy(path)
        self.assertEqual(pol["tiers"]["1"], ["ollama:example-small:8b"])
        self.assertEqual(pol["tiers"]["3"], POLICY["tiers"]["3"])
        self.assertEqual(pol["authority"], POLICY["authority"])

    def test_defaults_match_router_tiers(self):
        from desk.orchestrator import router
        for lvl in (1, 2, 3, 4):
            self.assertEqual(POLICY["tiers"][str(lvl)][0], "nvidia:" + router._DEFAULT_MODELS[lvl]["nvidia"])
            self.assertEqual(POLICY["thinking"][str(lvl)], router._DEFAULT_THINKING[lvl])
            self.assertEqual(POLICY["timeouts_s"][str(lvl)], router._DEFAULT_TIMEOUTS[lvl])


# ---------------------------------------------------------------------------------------------- bridges
class BridgeTests(unittest.TestCase):
    def test_agent_loop_runs_on_a_model_without_native_tools(self):
        from desk.orchestrator.agent_loop import run_agent
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state"))
            with open(os.path.join(d, "state", "sch_dump.json"), "w", encoding="utf-8") as f:
                json.dump({"parts": [{"ref": "C1", "pins": [{"num": "2", "net": "GND"}]}]}, f)
            fake = FakeProvider("local", ['{"tool_calls": [{"name": "list_schematic_nets", "arguments": {}}]}',
                                          '{"summary": "1 net"}'])
            reg = registry_with(fake, descriptors=[desc("local", "tiny", native_tools=False, structured_output=False)])
            with mock.patch("desk.orchestrator.providers.bridge.get_provider_registry", return_value=reg):
                run = run_agent("list nets", project=d, model="local:tiny")
            self.assertEqual(run.stopped_reason, "final")
            self.assertEqual(run.tool_calls, 1)
            self.assertEqual(run.final_json, {"summary": "1 net"})
            self.assertEqual(run.provider, "local:tiny")
            self.assertEqual(run.accounting["calls"], 2)
            self.assertTrue(os.path.exists(os.path.join(d, "state", "model_usage.jsonl")))
            self.assertIn('"GND": ["C1.2"]', fake.requests[1].messages[-1]["content"])

    def test_fallback_chain_through_chat_adapter(self):
        a = FakeProvider("a", [error_for_status(401, "no")])
        b = FakeProvider("b", ["final from b"])
        ad = adapter_for_model("a:m", ["b:m"], registry=registry_with(a, b))
        r = ad.chat_completion([{"role": "user", "content": "x"}], tools=TOOLS)
        self.assertEqual((r["message"]["content"], r["provider"]), ("final from b", "b"))
        self.assertEqual(set(r["usage"]), {"prompt_tokens", "completion_tokens", "total_tokens"})
        err = adapter_for_model("a:m", registry=registry_with(FakeProvider("a", [error_for_status(401, "no")])))
        self.assertIn("all model routes failed", err.chat_completion([{"role": "user", "content": "x"}])["error"])

    def test_task_adapter_serves_router_tier(self):
        from desk.orchestrator.protocol import TaskRequest
        from desk.orchestrator.router import CapabilityRouter, ProviderRegistry
        fake = FakeProvider("acme", ['{"archetype": "dc_dc"}'])
        reg = registry_with(fake, descriptors=[desc("acme", "small-1")])
        with mock.patch("desk.orchestrator.providers.allocation.POLICY", dict(POLICY, tiers={"1": ["acme:small-1"]})):
            self.assertEqual(register_with_router(["acme", "nvidia"], registry=reg), ["acme"])
        try:
            with mock.patch.dict(os.environ, {"DESK_PROVIDER_ORDER": "acme"}):
                res = CapabilityRouter.dispatch(TaskRequest(prompt="classify", execution_level=1,
                                                            output_schema={"type": "object"}))
            self.assertTrue(res.success, res.error)
            self.assertEqual((res.provider, res.model, res.output_json), ("acme", "small-1", {"archetype": "dc_dc"}))
            self.assertTrue(fake.requests[0].json_mode)
            self.assertFalse(ProviderTaskAdapter("missing", reg).check_health().available)
        finally:
            ProviderRegistry._providers.pop("acme", None)
            ProviderRegistry._health_cache.pop("acme", None)


# ---------------------------------------------------------------------------------------------- S-5 and config
class ProjectScopeTests(unittest.TestCase):
    def test_model_cannot_redirect_project(self):
        from desk.orchestrator import tools_manifest as tm
        seen = []
        with tempfile.TemporaryDirectory() as fixed, tempfile.TemporaryDirectory() as other, \
                mock.patch.dict(tm.HANDLERS, {"read_pcb": lambda a, c: seen.append(a["project"]) or {"ok": True}}):
            ctx = {"project": fixed, "allow_mutation": True}
            r = tm.dispatch("read_pcb", {"project": other}, ctx)
            self.assertIn("fixed by the operator", r["error"])
            self.assertEqual(seen, [])
            self.assertEqual(tm.dispatch("read_pcb", {"project": fixed + os.sep}, ctx), {"ok": True})
            self.assertEqual(tm.dispatch("read_pcb", {}, ctx), {"ok": True})
            self.assertEqual(seen, [fixed, fixed])
            r = tm.dispatch("wire_net", {"project": other, "net": "EN", "pins": ["U1.2"]}, ctx)
            self.assertIn("refused", r["error"])

    def test_wire_net_needs_operator_fixed_project(self):
        from desk.orchestrator import tools_manifest as tm
        r = tm.dispatch("wire_net", {"project": "p", "net": "EN", "pins": ["U1.2"]}, {"allow_mutation": True})
        self.assertIn("no operator-fixed project", r["error"])

    def test_new_config_keys(self):
        from desk.config import SECRET, setting_for
        for k in ("OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            self.assertEqual(setting_for(k).type, SECRET)
        self.assertIsNotNone(setting_for("DESK_OLLAMA_BASE_URL"))
        self.assertIsNotNone(setting_for("DESK_MODEL_POLICY_FILE"))
        self.assertIsNone(setting_for("DESK_FOO_BASE_URL"))


if __name__ == "__main__":
    unittest.main()
