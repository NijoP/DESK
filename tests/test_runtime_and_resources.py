"""Unit and Integration Tests for DESK Adaptive Runtime and Resource Management.
Covers:
- Cross-platform hardware detection
- Resource tier classification and budget derivation
- Simulated LOW, NORMAL, HIGH hardware modes
- Task scheduler with single-writer mutation serialization
- Bounded process execution & timeout guards
- Checkpoint management and atomic recovery.
"""
import unittest
import time
import os
import shutil
import threading
from desk.runtime.resource_profile import ResourceDetector, HardwareProfile
from desk.runtime.budget import BudgetManager, ExecutionBudget
from desk.runtime.scheduler import TaskScheduler, TASK_EDA_MUTATION, TASK_PURE_CPU, TASK_EXTERNAL_PROCESS
from desk.runtime.process_guard import ProcessGuard
from desk.runtime.checkpoints import CheckpointManager

class TestRuntimeAndResources(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_runtime_test")
        os.makedirs(self.test_dir, exist_ok=True)
        ResourceDetector.set_simulated_tier(None)

    def tearDown(self):
        ResourceDetector.set_simulated_tier(None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_01_host_hardware_detection(self):
        hw = ResourceDetector.detect()
        self.assertGreater(hw.logical_cores, 0)
        self.assertGreater(hw.physical_ram_mb, 1024.0)
        self.assertIn(hw.resource_tier, ("LOW", "NORMAL", "HIGH"))
        self.assertIsInstance(hw.memory_pressure, bool)

    def test_02_simulated_low_resource_profile(self):
        # Simulate dual-core 8GB laptop
        ResourceDetector.set_simulated_tier("LOW")
        hw = ResourceDetector.detect()
        self.assertEqual(hw.logical_cores, 2)
        self.assertEqual(hw.resource_tier, "LOW")
        self.assertTrue(hw.is_simulated)

        budget = BudgetManager.derive_budget(hw)
        self.assertEqual(budget.tier, "LOW")
        self.assertEqual(budget.max_parallel_pure_cpu, 1)
        self.assertEqual(budget.max_external_processes, 1)
        self.assertLessEqual(budget.batch_size_components, 25)

    def test_03_simulated_high_resource_profile(self):
        # Simulate 16-core 64GB workstation
        ResourceDetector.set_simulated_tier("HIGH")
        hw = ResourceDetector.detect()
        self.assertEqual(hw.logical_cores, 16)
        self.assertEqual(hw.resource_tier, "HIGH")

        budget = BudgetManager.derive_budget(hw)
        self.assertEqual(budget.tier, "HIGH")
        self.assertGreaterEqual(budget.max_parallel_pure_cpu, 4)
        self.assertGreaterEqual(budget.max_external_processes, 2)
        self.assertGreaterEqual(budget.batch_size_components, 100)

    def test_04_scheduler_serializes_eda_mutations(self):
        scheduler = TaskScheduler()
        execution_order = []
        active_writers = []
        concurrency_violated = [False]

        def mutation_worker(writer_id: int):
            def work():
                if len(active_writers) > 0:
                    concurrency_violated[0] = True
                active_writers.append(writer_id)
                time.sleep(0.05)
                active_writers.remove(writer_id)
                execution_order.append(writer_id)
                return writer_id
            return scheduler.execute(TASK_EDA_MUTATION, work, task_id=f"write_{writer_id}")

        threads = [threading.Thread(target=mutation_worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertFalse(concurrency_violated[0], "Multiple writers entered EDA_MUTATION concurrently!")
        self.assertEqual(len(execution_order), 5)

    def test_05_process_guard_timeout_and_bounds(self):
        # Test command with small timeout
        import sys
        sleep_cmd = [sys.executable, "-c", "import time; time.sleep(1.0)"]
        res = ProcessGuard.run_bounded(sleep_cmd, timeout_s=0.1)
        self.assertTrue(res.timed_out)
        self.assertEqual(res.exit_code, -1)

    def test_06_checkpoint_manager_atomic_and_pruning(self):
        # Save checkpoints
        chk1 = CheckpointManager.save_checkpoint(self.test_dir, "placement", {"comps": 10}, max_history=2)
        time.sleep(0.01)
        chk2 = CheckpointManager.save_checkpoint(self.test_dir, "routing", {"routes": 20}, max_history=2)
        time.sleep(0.01)
        chk3 = CheckpointManager.save_checkpoint(self.test_dir, "copper", {"zones": 2}, max_history=2)

        # History should be pruned to 2
        chk_dir = os.path.join(self.test_dir, "state", "checkpoints")
        files = [f for f in os.listdir(chk_dir) if f.endswith(".json")]
        self.assertEqual(len(files), 2)

        # Latest should be copper
        latest = CheckpointManager.load_latest_checkpoint(self.test_dir)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["stage"], "copper")

if __name__ == "__main__":
    unittest.main()
