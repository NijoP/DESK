"""
Performance and resource overhead benchmark for DESK Mission Control.
Measures physical wall-clock latency and memory delta with server active vs inactive.
"""

import os
import sys
import time
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desk.models import NetEndpoint
from desk.router import RoutingPriorityScheduler
from desk.runtime.events import get_event_bus
from desk.runtime.resource_profile import ResourceDetector
from desk.runtime.server import DeskServer


def run_benchmark():
    # Setup test endpoints
    ep1 = NetEndpoint(ref="U1", pad_num="1", net="GND", x_mil=0.0, y_mil=0.0, layer=1)
    ep2 = NetEndpoint(ref="U2", pad_num="1", net="GND", x_mil=100.0, y_mil=100.0, layer=1)
    nets = {f"NET_{i}": [ep1, ep2] for i in range(100)}

    # 1. Baseline: 100 scheduling runs WITHOUT server
    t0 = time.perf_counter()
    for _ in range(100):
        RoutingPriorityScheduler.schedule_nets(nets)
    t_baseline = (time.perf_counter() - t0) * 1000  # ms total

    # 2. With DeskServer and EventBus active + SSE streaming connection
    server = DeskServer(host="127.0.0.1", port=49820)
    url, _ = server.start(background=True)
    time.sleep(0.05)

    bus = get_event_bus()

    # Connect an SSE listener
    req = urllib.request.Request(f"{url}/api/v1/events/stream")
    sse_conn = urllib.request.urlopen(req, timeout=5.0)

    t1 = time.perf_counter()
    for i in range(100):
        RoutingPriorityScheduler.schedule_nets(nets)
        if i % 10 == 0:
            bus.emit("stage.progress", stage="pcb_routing", progress=float(i), message=f"Iteration {i}")
    t_with_server = (time.perf_counter() - t1) * 1000  # ms total

    # Measure memory
    hw = ResourceDetector.detect()

    sse_conn.close()
    server.stop()

    print("--- BENCHMARK RESULTS ---")
    print(f"Baseline (Server Inactive, 100 runs):   {t_baseline:.2f} ms ({t_baseline/100:.3f} ms/run)")
    print(f"With Server & Events (100 runs + SSE): {t_with_server:.2f} ms ({t_with_server/100:.3f} ms/run)")
    delta_ms = t_with_server - t_baseline
    print(f"Overhead Delta:                        {delta_ms:.2f} ms total ({delta_ms/100:.3f} ms/op)")
    print(f"Process Memory:                        {hw.current_process_ram_mb:.1f} MB")
    print(f"Resource Tier:                         {hw.resource_tier}")


if __name__ == "__main__":
    run_benchmark()
