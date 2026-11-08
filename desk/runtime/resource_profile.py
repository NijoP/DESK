"""Adaptive Hardware and Resource Detection for DESK Runtime.
Detects CPU logical cores, physical RAM, available RAM, and memory pressure.
Works cross-platform on Windows and Linux/Ubuntu with zero external dependencies.
"""
import os
import sys
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class HardwareProfile:
    logical_cores: int
    physical_ram_mb: float
    available_ram_mb: float
    memory_pressure: bool
    platform: str
    resource_tier: str  # "LOW", "NORMAL", "HIGH"
    is_simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logical_cores": self.logical_cores,
            "physical_ram_mb": round(self.physical_ram_mb, 1),
            "available_ram_mb": round(self.available_ram_mb, 1),
            "memory_pressure": self.memory_pressure,
            "platform": self.platform,
            "resource_tier": self.resource_tier,
            "is_simulated": self.is_simulated
        }

class ResourceDetector:
    """Detects host system resources with conservative cross-platform fallbacks."""
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
                    physical_ram_mb=8192.0,
                    available_ram_mb=2048.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="LOW",
                    is_simulated=True
                )
            elif cls._simulated_tier == "HIGH":
                return HardwareProfile(
                    logical_cores=16,
                    physical_ram_mb=65536.0,
                    available_ram_mb=32768.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="HIGH",
                    is_simulated=True
                )
            else:
                return HardwareProfile(
                    logical_cores=6,
                    physical_ram_mb=16384.0,
                    available_ram_mb=8192.0,
                    memory_pressure=False,
                    platform=sys.platform,
                    resource_tier="NORMAL",
                    is_simulated=True
                )

        cores = os.cpu_count() or 2
        total_ram_mb = 8192.0
        avail_ram_mb = 4096.0
        platform_name = sys.platform

        if os.name == "nt":
            try:
                import ctypes
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
        elif sys.platform.startswith("linux"):
            try:
                with open("/proc/meminfo", "r") as f:
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

        # Memory pressure: available RAM < 15% or < 600 MB
        pressure = (avail_ram_mb < 600.0) or ((avail_ram_mb / max(1.0, total_ram_mb)) < 0.15)

        # Classification
        if cores <= 2 or total_ram_mb <= 8192.0:
            tier = "LOW"
        elif cores >= 8 and total_ram_mb >= 24576.0:
            tier = "HIGH"
        else:
            tier = "NORMAL"

        return HardwareProfile(
            logical_cores=cores,
            physical_ram_mb=round(total_ram_mb, 1),
            available_ram_mb=round(avail_ram_mb, 1),
            memory_pressure=pressure,
            platform=platform_name,
            resource_tier=tier,
            is_simulated=False
        )
