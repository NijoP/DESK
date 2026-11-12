"""T-16: image input for the OpenAI-compatible adapter and vision verification state in the registry."""
import base64
import os
import tempfile
import unittest
from unittest import mock

from desk.orchestrator.protocol import TaskRequest
from desk.orchestrator.http_adapter import OpenAICompatAdapter
from desk.orchestrator.capabilities import get_registry, ModelCapability, CapabilityRegistry
from desk.orchestrator import router


class ImageParts(unittest.TestCase):
    def test_no_images_keeps_plain_string_content(self):
        body = OpenAICompatAdapter("nvidia", api_key="k").build_body(TaskRequest(prompt="hi", preferred_model="m"))
        self.assertEqual(body["messages"][-1]["content"], "hi")

    def test_file_image_is_inlined_as_data_url(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "shot.png")
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfakepng")
        body = OpenAICompatAdapter("nvidia", api_key="k").build_body(TaskRequest(prompt="what", images=[p], preferred_model="m"))
        content = body["messages"][-1]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "what"})
        self.assertEqual(content[1]["type"], "image_url")
        url = content[1]["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(url.split(",", 1)[1])[:4], b"\x89PNG")

    def test_data_and_http_urls_pass_through(self):
        parts = OpenAICompatAdapter.user_content("p", ["data:image/jpeg;base64,AAAA", "https://x/y.png"])
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/jpeg;base64,AAAA")
        self.assertEqual(parts[2]["image_url"]["url"], "https://x/y.png")

    def test_task_request_round_trip_keeps_images(self):
        t = TaskRequest(prompt="p", images=["a.png"])
        self.assertEqual(TaskRequest.from_dict(t.to_dict()).images, ["a.png"])
        self.assertEqual(TaskRequest.from_dict({"prompt": "old dict without images"}).images, [])


class VisionRouting(unittest.TestCase):
    def test_images_force_a_vision_model(self):
        t = router._task_for(TaskRequest(prompt="p", images=["a.png"], execution_level=1), "pi", 1)
        self.assertTrue(t.requires_vision)
        self.assertEqual(t.preferred_model, "nvidia/nemotron-3.5-super-vl-120b-a12b")

    def test_registry_records_vision_verification_separately(self):
        e = get_registry().get("pi", "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.assertTrue(e.vision)
        self.assertEqual(e.vision_status, "VERIFIED")
        self.assertEqual(e.vision_verified_on, "2026-11-12")
        self.assertIn("vision_status", e.to_dict())
        agy = get_registry().get("agy", "gemini-3.8-flash-high")
        self.assertEqual(agy.vision_status, "UNVERIFIED")            # catalogue claim, never probed by DESK
        text_only = ModelCapability(provider="x", model_id="t", vision=False)
        self.assertEqual(text_only.vision_status, "NONE")
        self.assertEqual(CapabilityRegistry([text_only]).ensure_capability("x", "t", "vision"), None)


if __name__ == "__main__":
    unittest.main()
