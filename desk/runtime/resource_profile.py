"""Adaptive Hardware and Resource Detection for DESK Runtime.
Detects CPU logical cores, CPU affinity, physical RAM, available RAM, cgroup container limits,
current process memory, disk availability, and memory pressure.
Works cross-platform on Windows and Linux/Ubuntu with zero external dependencies.
"""
import ctypes
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class HardwareProfile:
    logical_cores: int
    cpu_affinity_count: int
    physical_ram_mb: float
    available_ram_mb: float
    cgroup_ram_limit_mb: Optional[float]
    current_process_ram_mb: float
    disk_free_mb: float
    memory_pressure: bool
    platform: str
    resource_tier: str  # "LOW", "NORMAL", "HIGH"
    is_simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_cores": self.logical_cores,
            "cpu_affinity_count": self.cpu_affinity_count,
            "physical_ram_mb": round(self.physical_ram_mb, 1),
            "available_ram_mb": round(self.available_ram_mb, 1),
            "cgroup_ram_limit_mb": round(self.cgroup_ram_limit_mb, 1) if self.cgroup_ram_limit_mb else None,
            "current_process_ram_mb": round(self.current_process_ram_mb, 1),
            "disk_free_mb": round(self.disk_free_mb, 1),
            "memory_pressure": self.memory_pressure,
            "platform": self.platform,
            "resource_tier": self.resource_tier,
            "is_simulated": self.is_simulated,
        }


class ResourceDetector:
    """Detects host and container system resources with conservative cross-platform fallbacks."""
    _simulated_tier: Optional[str] = None

    @classmethod
    def set_simulated_tier(cls, tier: Optional[str]):
        """Allows testing execution under simulated LOW, NORMAL, or HIGH resource profiles."""
        cls._simulated_tier = tier.upper() if tier else None

    @classmethod
    def detect(cls) -> HardwareProfile:
        if cls._simulated_tier:
            if cls._simulated_tier == "LOW":
                return HardwareProfile(
                    logical_cores=2,
                    cpu_affinity_count=2,
                    physical_ram_mb=8192.0,
                    available_ram_mb=2048.0,
                    cgroup_ram_limit_mb=None,
                    current_process_ram_mb=45.0,
                    disk_free_mb=10240.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="LOW",
                    is_simulated=True,
                )
            elif cls._simulated_tier == "HIGH":
                return HardwareProfile(
                    logical_cores=16,
                    cpu_affinity_count=16,
                    physical_ram_mb=65536.0,
                    available_ram_mb=32768.0,
                    cgroup_ram_limit_mb=None,
                    current_process_ram_mb=90.0,
                    disk_free_mb=102400.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="HIGH",
                    is_simulated=True,
                )
            else:
                return HardwareProfile(
                    logical_cores=6,
                    cpu_affinity_count=6,
                    physical_ram_mb=16384.0,
                    available_ram_mb=8192.0,
                    cgroup_ram_limit_mb=None,
                    current_process_ram_mb=60.0,
                    disk_free_mb=51200.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="NORMAL",
                    is_simulated=True,
                )

        cores = os.cpu_count() or 2
        affinity_count = cores
        if hasattr(os, "sched_getaffinity"):
            try:
                affinity_count = len(os.sched_getaffinity(0))
            except Exception:
                affinity_count = cores

        total_ram_mb = 8192.0
        avail_ram_mb = 4096.0
        cgroup_limit_mb: Optional[float] = None
        current_proc_mb = 50.0
        platform_name = sys.platform

        # 1. Host RAM Detection
        if os.name == "nt":
            try:
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                total_ram_mb = stat.ullTotalPhys / (1024 * 1024)
                avail_ram_mb = stat.ullAvailPhys / (1024 * 1024)
            except Exception:
                pass

            # Current Process Working Set on Windows
            try:
                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", ctypes.c_ulong),
                        ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]
                pmc = PROCESS_MEMORY_COUNTERS()
                pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                if ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(),
                    ctypes.byref(pmc),
                    pmc.cb,
                ):
                    current_proc_mb = pmc.WorkingSetSize / (1024 * 1024)
            except Exception:
                pass

        elif sys.platform.startswith("linux"):
            try:
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            key = parts[0].strip()
                            val = parts[1].strip().split()[0]
                            meminfo[key] = int(val)
                    if "MemTotal" in meminfo:
                        total_ram_mb = meminfo["MemTotal"] / 1024.0
                    if "MemAvailable" in meminfo:
                        avail_ram_mb = meminfo["MemAvailable"] / 1024.0
                    elif "MemFree" in meminfo:
                        avail_ram_mb = meminfo["MemFree"] / 1024.0
            except Exception:
                pass

            # Cgroup v2 limit
            cgroup_v2 = "/sys/fs/cgroup/memory.max"
            if os.path.exists(cgroup_v2):
                try:
                    with open(cgroup_v2, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if val != "max" and val.isdigit():
                            cgroup_limit_mb = int(val) / (1024 * 1024)
                except Exception:
                    pass

            # Cgroup v1 limit
            cgroup_v1 = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
            if cgroup_limit_mb is None and os.path.exists(cgroup_v1):
                try:
                    with open(cgroup_v1, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if val.isdigit() and int(val) < 10**15:
                            cgroup_limit_mb = int(val) / (1024 * 1024)
                except Exception:
                    pass

            # If cgroup limit is active and smaller than physical RAM, clamp total
            if cgroup_limit_mb is not None and cgroup_limit_mb < total_ram_mb:
                total_ram_mb = cgroup_limit_mb
                avail_ram_mb = min(avail_ram_mb, cgroup_limit_mb)

            # Linux Process RSS
            try:
                with open("/proc/self/statm", "r", encoding="utf-8") as f:
                    fields = f.read().split()
                    if len(fields) >= 2:
                        pages = int(fields[1])
                        page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
                        current_proc_mb = (pages * page_size) / (1024 * 1024)
            except Exception:
                pass

        # 2. Disk Availability
        disk_free_mb = 10240.0
        try:
            _, _, free_b = shutil.disk_usage(os.getcwd())
            disk_free_mb = free_b / (1024 * 1024)
        except Exception:
            pass

        # 3. Memory Pressure: available RAM < 600 MB or < 15%, or disk < 500 MB
        pressure = (avail_ram_mb < 600.0) or ((avail_ram_mb / max(1.0, total_ram_mb)) < 0.15) or (disk_free_mb < 500.0)

        # 4. Effective capacity considering affinity
        effective_cores = min(cores, affinity_count)

        # 5. Tier Classification
        if pressure or effective_cores <= 2 or total_ram_mb <= 8192.0 or avail_ram_mb < 1500.0:
            tier = "LOW"
        elif effective_cores >= 8 and total_ram_mb >= 24576.0 and avail_ram_mb >= 8192.0:
            tier = "HIGH"
        else:
            tier = "NORMAL"

        return HardwareProfile(
            logical_cores=cores,
            cpu_affinity_count=affinity_count,
            physical_ram_mb=round(total_ram_mb, 1),
            available_ram_mb=round(avail_ram_mb, 1),
            cgroup_ram_limit_mb=cgroup_limit_mb,
            current_process_ram_mb=round(current_proc_mb, 1),
            disk_free_mb=round(disk_free_mb, 1),
            memory_pressure=pressure,
            platform=platform_name,
            resource_tier=tier,
            is_simulated=False,
        )
