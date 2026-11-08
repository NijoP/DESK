"""
Unit tests for DESK Mission Control Local HTTP Server, REST API, and SSE Streaming.
"""

import json
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request

from desk.runtime.events import EventBus, get_event_bus
from desk.runtime.projection import get_execution_projection
from desk.runtime.server import DeskServer


class TestDeskServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Use an ephemeral high port range for tests
        cls.server = DeskServer(host="127.0.0.1", port=49700)
        cls.url, cls.port = cls.server.start(background=True)
        # Give thread time to bind
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _fetch(self, path: str, headers: dict = None) -> tuple[int, bytes, dict]:
        req = urllib.request.Request(f"{self.url}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_health_endpoint(self):
        code, body, _ = self._fetch("/api/v1/health")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "HEALTHY")
        self.assertEqual(data["service"], "DESK Mission Control")

    def test_status_endpoint(self):
        code, body, _ = self._fetch("/api/v1/status")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("status", data)
        self.assertIn("overall_progress", data)
        self.assertIn("stages", data)
        self.assertEqual(len(data["stages"]), 12)
        self.assertIn("metrics", data)

    def test_projects_endpoint(self):
        code, body, _ = self._fetch("/api/v1/projects")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIsInstance(data, list)

    def test_metrics_endpoint(self):
        code, body, _ = self._fetch("/api/v1/metrics")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("logical_cores", data)
        self.assertIn("physical_ram_mb", data)
        self.assertIn("current_process_ram_mb", data)

    def test_executions_endpoint(self):
        code, body, _ = self._fetch("/api/v1/executions")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_execution_details_and_subroutes(self):
        proj = get_execution_projection()
        exec_id = proj.execution_id

        # 1. Execution summary
        code, body, _ = self._fetch(f"/api/v1/executions/{exec_id}")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["execution_id"], exec_id)

        # 2. Events timeline
        code, body, _ = self._fetch(f"/api/v1/executions/{exec_id}/events")
        self.assertEqual(code, 200)
        events = json.loads(body.decode("utf-8"))
        self.assertIsInstance(events, list)

        # 3. Logs
        code, body, _ = self._fetch(f"/api/v1/executions/{exec_id}/logs")
        self.assertEqual(code, 200)
        logs = json.loads(body.decode("utf-8"))
        self.assertIsInstance(logs, list)

        # 4. Unknown execution ID returns 404
        code, body, _ = self._fetch("/api/v1/executions/unknown_id_9999")
        self.assertEqual(code, 404)

    def test_path_traversal_protection(self):
        code, body, _ = self._fetch("/api/v1/executions/../../../windows/win.ini")
        self.assertEqual(code, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("Potential path traversal", data["error"])

    def test_security_headers_present(self):
        code, _, headers = self._fetch("/api/v1/health")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", headers)

    def test_dashboard_asset_served(self):
        code, body, headers = self._fetch("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b"DESK Local Mission Control", body)

    def test_port_collision_resolution(self):
        # Occupy port 49750
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 49750))
        sock.listen(1)

        try:
            # DeskServer requested port 49750 should bump to 49751
            srv = DeskServer(host="127.0.0.1", port=49750)
            url, port = srv.start(background=True)
            self.assertEqual(port, 49751)
            self.assertIn("49751", url)
            srv.stop()
        finally:
            sock.close()

    def test_sse_stream_and_graceful_disconnect(self):
        # Connect to SSE stream endpoint
        req = urllib.request.Request(f"{self.url}/api/v1/events/stream")
        stream_resp = urllib.request.urlopen(req, timeout=5.0)

        self.assertEqual(stream_resp.status, 200)
        self.assertIn("text/event-stream", stream_resp.headers.get("Content-Type", ""))

        # Emit an event on the bus in a separate thread
        bus = get_event_bus()

        def push_event():
            time.sleep(0.1)
            bus.emit("stage.progress", stage="pcb_routing", progress=75.0, message="Testing SSE push")

        t = threading.Thread(target=push_event)
        t.start()

        # Read line from SSE stream
        line = stream_resp.readline().decode("utf-8")
        self.assertTrue(line.startswith("id:") or line.startswith(":") or line.startswith("event:") or line.startswith("data:"))

        # Close client stream cleanly
        stream_resp.close()
        t.join()


class TestEngineeringIntegrity(unittest.TestCase):

    def test_dashboard_disconnection_does_not_interrupt_routing(self):
        """Validates that a client disconnecting from SSE does not abort routing or pipeline execution."""
        from desk.router import RoutingPriorityScheduler

        # Start a local test server
        server = DeskServer(host="127.0.0.1", port=49780)
        url, _ = server.start(background=True)
        time.sleep(0.05)

        try:
            # 1. Connect a client to SSE
            req = urllib.request.Request(f"{url}/api/v1/events/stream")
            client = urllib.request.urlopen(req, timeout=3.0)

            # 2. Force abrupt disconnection by closing socket
            client.close()

            # 3. Execute real router operations
            from desk.models import NetEndpoint
            ep1 = NetEndpoint(ref="U1", pad_num="1", net="GND", x_mil=0.0, y_mil=0.0, layer=1)
            ep2 = NetEndpoint(ref="U2", pad_num="1", net="GND", x_mil=100.0, y_mil=100.0, layer=1)
            nets = {"GND": [ep1, ep2], "USB_D_P": [ep1, ep2], "USB_D_N": [ep1, ep2], "3V3": [ep1, ep2]}
            stages = RoutingPriorityScheduler.schedule_nets(
                nets,
                diff_pairs={"USB": ("USB_D_P", "USB_D_N")},
                high_current={"3V3": 1.5}
            )

            # Routing scheduler must succeed completely without exceptions
            self.assertIn("GND", stages[1])
            self.assertIn("USB_D_P", stages[3])
            self.assertIn("3V3", stages[5])
        finally:
            server.stop()

    def test_monitoring_endpoints_are_strictly_read_only(self):
        """Validates that POST / PUT / DELETE mutations are refused."""
        server = DeskServer(host="127.0.0.1", port=49790)
        url, _ = server.start(background=True)
        time.sleep(0.05)

        try:
            # Try POSTing to status
            req = urllib.request.Request(f"{url}/api/v1/status", data=b'{"mutate": true}', method="POST")
            try:
                with urllib.request.urlopen(req) as resp:
                    self.fail("Expected HTTP error on POST")
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, [405, 501])
        finally:
            server.stop()

    def test_missing_verification_evidence_never_becomes_pass(self):
        """Validates that unrun verification remains NOT_RUN or PENDING and never turns into PASS."""
        proj = get_execution_projection()
        summary = proj.get_summary()
        res = summary["engineering_results"]

        # In unexecuted state, gates must remain NOT_RUN
        self.assertEqual(res["quality_gates"]["gate_1_shorts"], "NOT_RUN")
        self.assertNotEqual(res["final_acceptance_state"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
