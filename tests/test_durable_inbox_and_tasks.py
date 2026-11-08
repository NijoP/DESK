"""
Unit tests for the Durable Task Inbox, 12-State Machine, and Event Supervisor.
"""

import unittest

from desk.operation_registry import ReplayPolicy
from desk.runtime.events import EventBus, get_event_bus
from desk.runtime.task_inbox import TaskInbox, get_task_inbox
from desk.runtime.task_state import TaskState, TaskStateMachine


class TestDurableInboxAndTasks(unittest.TestCase):
    def test_state_machine_valid_lifecycle(self):
        sm = TaskStateMachine(TaskState.QUEUED, task_id="test_tsk_001")
        self.assertEqual(sm.current_state, TaskState.QUEUED)

        sm.transition_to(TaskState.PREPARING, reason="Resource allocated")
        self.assertEqual(sm.current_state, TaskState.PREPARING)

        sm.transition_to(TaskState.RUNNING, reason="Executing router")
        self.assertEqual(sm.current_state, TaskState.RUNNING)

        sm.transition_to(TaskState.VALIDATING, reason="Running M6 quality gates")
        self.assertEqual(sm.current_state, TaskState.VALIDATING)

        sm.transition_to(TaskState.COMPLETED, reason="Quality gates passed")
        self.assertEqual(sm.current_state, TaskState.COMPLETED)
        self.assertTrue(sm.is_terminal())

    def test_state_machine_illegal_transition(self):
        sm = TaskStateMachine(TaskState.QUEUED, task_id="test_tsk_002")
        # Direct transition from QUEUED to COMPLETED is prohibited
        with self.assertRaises(ValueError):
            sm.transition_to(TaskState.COMPLETED, reason="Skipping work")

    def test_event_bus_emission_and_subscription(self):
        bus = EventBus()
        captured_events = []

        bus.subscribe("task.started", lambda e: captured_events.append(e))
        bus.subscribe("*", lambda e: captured_events.append(e))

        evt = bus.emit("task.started", task_id="tsk_99", payload={"stage": "M3"})
        self.assertEqual(evt.event_type, "task.started")
        self.assertEqual(len(captured_events), 2)  # 1 specific + 1 wildcard

        history = bus.get_history(task_id="tsk_99")
        self.assertEqual(len(history), 1)

    def test_task_inbox_monotonic_and_idempotency(self):
        inbox = TaskInbox()

        t1 = inbox.submit(
            task_type="route_net",
            payload={"net": "USB_DP", "width": 0.254},
            profile_revision="rev_1",
            replay_policy=ReplayPolicy.SAFE_IDEMPOTENT,
        )
        self.assertEqual(t1.sequence_number, 1)
        self.assertEqual(t1.current_state, TaskState.QUEUED)

        # Submitting the identical idempotent task returns existing task message
        t2 = inbox.submit(
            task_type="route_net",
            payload={"net": "USB_DP", "width": 0.254},
            profile_revision="rev_1",
            replay_policy=ReplayPolicy.SAFE_IDEMPOTENT,
        )
        self.assertEqual(t1.task_id, t2.task_id)
        self.assertEqual(t2.sequence_number, 1)

        # Different payload creates next monotonic task
        t3 = inbox.submit(
            task_type="route_net",
            payload={"net": "USB_DN", "width": 0.254},
            profile_revision="rev_1",
        )
        self.assertEqual(t3.sequence_number, 2)
        self.assertNotEqual(t1.task_id, t3.task_id)

    def test_task_acknowledgment(self):
        inbox = TaskInbox()
        task = inbox.submit("test_op", {"param": 1})
        self.assertFalse(task.acknowledged)

        inbox.acknowledge(task.task_id)
        self.assertTrue(task.acknowledged)
        self.assertIsNotNone(task.ack_timestamp)


if __name__ == "__main__":
    unittest.main()
