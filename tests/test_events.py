"""
Unit tests for DESK EventBus and Event streaming primitives.
"""

import unittest
from desk.runtime.events import Event, EventBus, get_event_bus


class TestEventBus(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus(max_history=10)

    def test_event_creation_and_serialization(self):
        ev = Event(
            event_type="stage.progress",
            task_id="task_1",
            stage="pcb_routing",
            task="route_critical_nets",
            status="running",
            progress=45.5,
            message="Routing net GND",
            metrics={"nets_routed": 12},
        )
        d = ev.to_dict()
        self.assertEqual(d["event_type"], "stage.progress")
        self.assertEqual(d["stage"], "pcb_routing")
        self.assertEqual(d["progress"], 45.5)
        self.assertEqual(d["metrics"]["nets_routed"], 12)
        self.assertIn("iso_timestamp", d)

    def test_event_ordering_and_history(self):
        for i in range(5):
            self.bus.emit("test.event", task_id=f"t_{i}", message=f"msg {i}")

        history = self.bus.get_history()
        self.assertEqual(len(history), 5)
        for i, ev in enumerate(history):
            self.assertEqual(ev.task_id, f"t_{i}")
            self.assertEqual(ev.message, f"msg {i}")

    def test_queue_saturation_and_pruning(self):
        # max_history is 10
        for i in range(15):
            self.bus.emit("overflow.event", task_id=f"t_{i}")

        history = self.bus.get_history()
        self.assertEqual(len(history), 10)
        self.assertEqual(history[0].task_id, "t_5")
        self.assertEqual(history[-1].task_id, "t_14")

    def test_subscribe_and_unsubscribe(self):
        calls = []

        def cb(e):
            calls.append(e)

        self.bus.subscribe("my.event", cb)
        self.bus.emit("my.event", task_id="1")
        self.assertEqual(len(calls), 1)

        # Unsubscribe
        res = self.bus.unsubscribe("my.event", cb)
        self.assertTrue(res)

        self.bus.emit("my.event", task_id="2")
        self.assertEqual(len(calls), 1)  # No new call

    def test_replay_with_last_event_id(self):
        e1 = self.bus.emit("stage.start", stage="M1")
        e2 = self.bus.emit("stage.progress", stage="M1", progress=50.0)
        e3 = self.bus.emit("stage.complete", stage="M1")

        # Replay since e1
        replayed = self.bus.get_events_since(e1.event_id)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[0].event_id, e2.event_id)
        self.assertEqual(replayed[1].event_id, e3.event_id)

        # Replay without last_event_id
        all_recent = self.bus.get_events_since(None)
        self.assertEqual(len(all_recent), 3)

    def test_listener_exception_isolation(self):
        def faulty(e):
            raise RuntimeError("Listener boom")

        passed = []
        def working(e):
            passed.append(e)

        self.bus.subscribe("faulty.test", faulty)
        self.bus.subscribe("faulty.test", working)

        # Should not raise exception
        ev = self.bus.emit("faulty.test", message="safe")
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0].message, "safe")


if __name__ == "__main__":
    unittest.main()
