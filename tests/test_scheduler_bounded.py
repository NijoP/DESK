"""
Unit tests for the Bounded, Resource-Aware TaskScheduler in desk/runtime/scheduler.py.
"""

import threading
import time
import unittest

from desk.runtime.scheduler import (
    QueueBackpressureError,
    TASK_EDA_MUTATION,
    TASK_PURE_CPU,
    TASK_VALIDATION,
    TaskPriority,
    TaskScheduler,
)


class TestSchedulerBounded(unittest.TestCase):
    def test_priority_and_execution(self):
        sched = TaskScheduler(max_queue_depth=50)
        res = sched.execute(TASK_PURE_CPU, lambda: 21 * 2, priority=TaskPriority.HIGH)
        self.assertEqual(res, 42)

    def test_backpressure_enforcement(self):
        # Create a tiny scheduler with max queue depth = 2 and workers paused
        sched = TaskScheduler(max_queue_depth=2)
        sched._running = False  # Workers don't dequeue

        # Fill the queue
        sched.submit(TASK_PURE_CPU, lambda: 1)
        sched.submit(TASK_PURE_CPU, lambda: 2)

        # 3rd submission must trigger backpressure
        with self.assertRaises(QueueBackpressureError):
            sched.submit(TASK_PURE_CPU, lambda: 3)

        sched.shutdown(wait=False)

    def test_dependency_chain(self):
        sched = TaskScheduler()

        # Task 1 writes data
        t1 = sched.submit(TASK_PURE_CPU, lambda: 100)

        # Task 2 depends on Task 1
        t2_res = sched.execute(
            TASK_PURE_CPU,
            lambda: sched.get_record(t1).result + 50,
            dependencies=[t1],
        )
        self.assertEqual(t2_res, 150)
        sched.shutdown(wait=False)

    def test_eda_mutation_serialization(self):
        sched = TaskScheduler()
        active_mutations = 0
        max_concurrent_mutations = 0
        lock = threading.Lock()

        def _mutation_fn():
            nonlocal active_mutations, max_concurrent_mutations
            with lock:
                active_mutations += 1
                if active_mutations > max_concurrent_mutations:
                    max_concurrent_mutations = active_mutations
            time.sleep(0.05)
            with lock:
                active_mutations -= 1
            return True

        threads = []
        for _ in range(5):
            t = threading.Thread(target=lambda: sched.execute(TASK_EDA_MUTATION, _mutation_fn))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # EDA mutations must NEVER exceed 1 concurrent execution
        self.assertEqual(max_concurrent_mutations, 1)
        sched.shutdown(wait=False)

    def test_task_cancellation(self):
        sched = TaskScheduler(max_queue_depth=10)
        sched._running = False  # Workers paused
        tid = sched.submit(TASK_PURE_CPU, lambda: 42)

        cancelled = sched.cancel_task(tid)
        self.assertTrue(cancelled)

        rec = sched.get_record(tid)
        self.assertEqual(rec.state, "CANCELLED")
        sched.shutdown(wait=False)

    def test_structured_telemetry(self):
        sched = TaskScheduler()
        for i in range(5):
            sched.execute(TASK_PURE_CPU, lambda: i * 2)

        telemetry = sched.get_telemetry()
        self.assertEqual(telemetry["completed_count"], 5)
        self.assertGreaterEqual(telemetry["duration_p50_ms"], 0.0)
        self.assertGreaterEqual(telemetry["duration_p95_ms"], 0.0)
        sched.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
