"""DESK Unified Ecosystem Settings and Health Dashboard.

Audits and reports readiness across:
1. Secure Credential Vault (Windows Credential Manager / Keychain / POSIX Vault)
2. EDA Environments (EasyEDA Pro CLI, Fast IPC Bridge, KiCad)
3. Sourcing Distributors (LCSC, Mouser, DigiKey)
4. Manufacturing Services (JLCPCB PCB & PCBA)
"""

from __future__ import annotations
import os
import sys
import shutil
import socket
from typing import Dict, Any, List
from desk.auth.broker import get_credential_broker, ProviderStatus
from desk.eda.easyeda_pro import get_easyeda_manager


class EcosystemDashboard:
    """Aggregates system-wide provider readiness and health status."""

    def __init__(self):
        self.broker = get_credential_broker()
        self.eda_mgr = get_easyeda_manager()

    def get_vault_status(self) -> Dict[str, Any]:
        from desk.auth.storage import (
            WindowsCredentialStore,
            MacOSCredentialStore,
            ProtectedFileCredentialStore,
            InMemoryCredentialStore,
        )
        store = self.broker._store
        if isinstance(store, WindowsCredentialStore):
            backend = "Windows Credential Manager (Advapi32.dll)"
        elif isinstance(store, MacOSCredentialStore):
            backend = "macOS Keychain Services"
        elif isinstance(store, ProtectedFileCredentialStore):
            backend = "POSIX 0600 Protected File Vault"
        elif isinstance(store, InMemoryCredentialStore):
            backend = "Sandboxed Ephemeral Memory"
        else:
            backend = type(store).__name__

        return {
            "backend": backend,
            "status": "HEALTHY",
            "items_configured": len(self.broker.list_credentials()),
        }

    def get_eda_status(self) -> Dict[str, Any]:
        cli_doc = self.eda_mgr.cli.doctor()
        
        # Fast socket test for local bridge port
        bridge_active = False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            if s.connect_ex(("127.0.0.1", 49620)) == 0:
                bridge_active = True
            s.close()
        except OSError:
            pass

        kicad_path = shutil.which("kicad-cli") or shutil.which("kicad")

        return {
            "easyeda_cli": cli_doc.get("status", "NOT_INSTALLED"),
            "easyeda_bridge": "ONLINE" if bridge_active else "OFFLINE",
            "kicad": "AVAILABLE" if kicad_path else "NOT_FOUND",
        }

    def get_suppliers_status(self) -> List[Dict[str, Any]]:
        suppliers = ["lcsc", "mouser", "digikey"]
        return [self.broker.get_provider_status(s) for s in suppliers]

    def get_manufacturing_status(self) -> List[Dict[str, Any]]:
        mfrs = ["jlcpcb"]
        return [self.broker.get_provider_status(m) for m in mfrs]

    def render_dashboard(self) -> str:
        """Render formatted console dashboard."""
        v = self.get_vault_status()
        eda = self.get_eda_status()
        suppliers = self.get_suppliers_status()
        mfrs = self.get_manufacturing_status()

        lines = []
        lines.append("=" * 78)
        lines.append("                  DESK ECOSYSTEM READINESS DASHBOARD                  ")
        lines.append("=" * 78)

        # 1. Vault
        lines.append(f"\n[1] OS CREDENTIAL SECURITY VAULT")
        lines.append(f"  Backend: {v['backend']}")
        lines.append(f"  Status:  {v['status']} ({v['items_configured']} service accounts configured)")

        # 2. EDA Tools
        lines.append(f"\n[2] ELECTRONICS DESIGN AUTOMATION (EDA)")
        lines.append(f"  EasyEDA Pro CLI:      {eda['easyeda_cli']}")
        lines.append(f"  EasyEDA IPC Bridge:   {eda['easyeda_bridge']} (port 49620)")
        lines.append(f"  KiCad CLI Engine:     {eda['kicad']}")

        # 3. Component Suppliers
        lines.append(f"\n[3] COMPONENT INTELLIGENCE & SOURCING")
        lines.append(f"  {'PROVIDER':<12} {'STATUS':<20} {'DETAILS / REMEDIATION'}")
        lines.append(f"  {'-'*12} {'-'*20} {'-'*40}")
        for s in suppliers:
            remediation = s.get("remediation") or "Ready"
            lines.append(f"  {s['service']:<12} {s['status']:<20} {remediation}")

        # 4. Manufacturing
        lines.append(f"\n[4] PCB & PCBA MANUFACTURING")
        lines.append(f"  {'FABRICATOR':<12} {'STATUS':<20} {'DETAILS / REMEDIATION'}")
        lines.append(f"  {'-'*12} {'-'*20} {'-'*40}")
        for m in mfrs:
            remediation = m.get("remediation") or "Ready"
            lines.append(f"  {m['service']:<12} {m['status']:<20} {remediation}")

        lines.append("\n" + "=" * 78)
        return "\n".join(lines)


def run_settings_cli():
    """CLI entrypoint for 'desk settings'."""
    dash = EcosystemDashboard()
    print(dash.render_dashboard())
