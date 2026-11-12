"""DESK OS-Native Secure Credential Storage.

Provides cross-platform access to native OS credential vaults with zero external
dependencies (pure Python standard library):
- Windows: Windows Credential Manager via Advapi32.dll (CredWriteW, CredReadW, CredDeleteW)
- macOS: Keychain Services via /usr/bin/security
- Linux / POSIX: Protected File Credential Store (0600 mode) or Secret Service
- In-Memory: Ephemeral storage for tests and sandboxed runs
"""

from __future__ import annotations
import os
import sys
import json
import base64
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseCredentialStore(ABC):
    """Abstract base class for secure credential storage."""

    @abstractmethod
    def get(self, service: str, account: str) -> Optional[str]:
        """Retrieve a credential secret."""
        pass

    @abstractmethod
    def set(self, service: str, account: str, secret: str) -> bool:
        """Store or update a credential secret."""
        pass

    @abstractmethod
    def delete(self, service: str, account: str) -> bool:
        """Delete a credential secret."""
        pass

    @abstractmethod
    def list(self) -> List[Dict[str, str]]:
        """List stored credentials (excluding secrets)."""
        pass


class WindowsCredentialStore(BaseCredentialStore):
    """Windows Credential Manager implementation using Advapi32.dll via ctypes."""

    PREFIX = "DESK"

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._advapi32 = ctypes.windll.advapi32

        # Define structures and function signatures
        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self._CREDENTIAL = CREDENTIAL
        self._PCREDENTIAL = ctypes.POINTER(CREDENTIAL)

        self._advapi32.CredWriteW.argtypes = [self._PCREDENTIAL, wintypes.DWORD]
        self._advapi32.CredWriteW.restype = wintypes.BOOL

        self._advapi32.CredReadW.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(self._PCREDENTIAL),
        ]
        self._advapi32.CredReadW.restype = wintypes.BOOL

        self._advapi32.CredFree.argtypes = [ctypes.c_void_p]
        self._advapi32.CredFree.restype = None

        self._advapi32.CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi32.CredDeleteW.restype = wintypes.BOOL

    def _target_name(self, service: str, account: str) -> str:
        return f"{self.PREFIX}:{service}:{account}"

    def get(self, service: str, account: str) -> Optional[str]:
        target = self._target_name(service, account)
        pcred = self._PCREDENTIAL()
        # CRED_TYPE_GENERIC = 1
        ok = self._advapi32.CredReadW(target, 1, 0, self._ctypes.byref(pcred))
        if not ok:
            return None
        try:
            raw_bytes = self._ctypes.string_at(
                pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize
            )
            return raw_bytes.decode("utf-16le")
        except Exception:
            return None
        finally:
            self._advapi32.CredFree(pcred)

    def set(self, service: str, account: str, secret: str) -> bool:
        target = self._target_name(service, account)
        encoded = secret.encode("utf-16le")
        blob = (self._ctypes.c_byte * len(encoded))(*encoded)

        # CRED_PERSIST_LOCAL_MACHINE = 2
        cred = self._CREDENTIAL(
            Flags=0,
            Type=1,
            TargetName=target,
            Comment="DESK Autonomous Engineering Vault",
            CredentialBlobSize=len(encoded),
            CredentialBlob=blob,
            Persist=2,
            AttributeCount=0,
            Attributes=None,
            TargetAlias=None,
            UserName=account,
        )
        return bool(self._advapi32.CredWriteW(self._ctypes.byref(cred), 0))

    def delete(self, service: str, account: str) -> bool:
        target = self._target_name(service, account)
        return bool(self._advapi32.CredDeleteW(target, 1, 0))

    def list(self) -> List[Dict[str, str]]:
        # Index tracking stored in local user metadata index file to enable fast enumeration
        meta_file = _get_metadata_index_file()
        if not os.path.exists(meta_file):
            return []
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("credentials", [])
        except Exception:
            return []


class MacOSCredentialStore(BaseCredentialStore):
    """macOS Keychain implementation via the /usr/bin/security tool."""

    PREFIX = "DESK"

    def _service_name(self, service: str) -> str:
        return f"{self.PREFIX}:{service}"

    def get(self, service: str, account: str) -> Optional[str]:
        import subprocess
        cmd = [
            "/usr/bin/security",
            "find-generic-password",
            "-s", self._service_name(service),
            "-a", account,
            "-w",
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return res.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def set(self, service: str, account: str, secret: str) -> bool:
        import subprocess
        cmd = [
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s", self._service_name(service),
            "-a", account,
            "-w", secret,
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def delete(self, service: str, account: str) -> bool:
        import subprocess
        cmd = [
            "/usr/bin/security",
            "delete-generic-password",
            "-s", self._service_name(service),
            "-a", account,
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def list(self) -> List[Dict[str, str]]:
        meta_file = _get_metadata_index_file()
        if not os.path.exists(meta_file):
            return []
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("credentials", [])
        except Exception:
            return []


class ProtectedFileCredentialStore(BaseCredentialStore):
    """Secure local file storage with strict POSIX permissions (0600 mode) and machine-salted encoding."""

    def __init__(self, filepath: Optional[str] = None):
        if filepath is None:
            desk_dir = os.path.expanduser(os.path.join("~", ".desk"))
            os.makedirs(desk_dir, exist_ok=True)
            self.filepath = os.path.join(desk_dir, "vault.json")
        else:
            self.filepath = filepath
        self._ensure_secure_file()

    def _ensure_secure_file(self):
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({}, f)
            if hasattr(os, "chmod"):
                try:
                    os.chmod(self.filepath, 0o600)
                except Exception:
                    pass

    def _obfuscate(self, secret: str) -> str:
        # Reversible local obfuscation keyed to user path (not cryptographic protection,
        # filesystem permissions provide the primary OS boundary)
        salt = hashlib.sha256(self.filepath.encode("utf-8")).digest()
        secret_bytes = secret.encode("utf-8")
        obf = bytes([b ^ salt[i % len(salt)] for i, b in enumerate(secret_bytes)])
        return base64.b64encode(obf).decode("ascii")

    def _deobfuscate(self, text: str) -> str:
        try:
            salt = hashlib.sha256(self.filepath.encode("utf-8")).digest()
            obf = base64.b64decode(text.encode("ascii"))
            plain = bytes([b ^ salt[i % len(salt)] for i, b in enumerate(obf)])
            return plain.decode("utf-8")
        except Exception:
            return ""

    def _read_data(self) -> Dict[str, Any]:
        if not os.path.exists(self.filepath):
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_data(self, data: Dict[str, Any]):
        tmp_file = self.filepath + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if hasattr(os, "chmod"):
            try:
                os.chmod(tmp_file, 0o600)
            except Exception:
                pass
        os.replace(tmp_file, self.filepath)

    def get(self, service: str, account: str) -> Optional[str]:
        data = self._read_data()
        key = f"{service}::{account}"
        if key in data:
            return self._deobfuscate(data[key].get("secret", ""))
        return None

    def set(self, service: str, account: str, secret: str) -> bool:
        data = self._read_data()
        key = f"{service}::{account}"
        data[key] = {
            "service": service,
            "account": account,
            "secret": self._obfuscate(secret),
            "updated_at": _get_timestamp(),
        }
        self._write_data(data)
        return True

    def delete(self, service: str, account: str) -> bool:
        data = self._read_data()
        key = f"{service}::{account}"
        if key in data:
            del data[key]
            self._write_data(data)
            return True
        return False

    def list(self) -> List[Dict[str, str]]:
        data = self._read_data()
        return [
            {"service": v.get("service", ""), "account": v.get("account", ""), "updated_at": v.get("updated_at", "")}
            for v in data.values()
        ]


class InMemoryCredentialStore(BaseCredentialStore):
    """Ephemeral in-memory store for unit testing and CI pipelines."""

    def __init__(self):
        self._store: Dict[str, Dict[str, str]] = {}

    def get(self, service: str, account: str) -> Optional[str]:
        key = f"{service}::{account}"
        return self._store.get(key, {}).get("secret")

    def set(self, service: str, account: str, secret: str) -> bool:
        key = f"{service}::{account}"
        self._store[key] = {
            "service": service,
            "account": account,
            "secret": secret,
            "updated_at": _get_timestamp(),
        }
        return True

    def delete(self, service: str, account: str) -> bool:
        key = f"{service}::{account}"
        if key in self._store:
            del self._store[key]
            return True
        return False

    def list(self) -> List[Dict[str, str]]:
        return [
            {"service": v["service"], "account": v["account"], "updated_at": v["updated_at"]}
            for v in self._store.values()
        ]


def _get_timestamp() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_metadata_index_file() -> str:
    desk_dir = os.path.expanduser(os.path.join("~", ".desk"))
    os.makedirs(desk_dir, exist_ok=True)
    return os.path.join(desk_dir, "credentials_index.json")


def update_metadata_index(service: str, account: str, action: str):
    """Maintain a sanitized index of configured services without secrets."""
    meta_file = _get_metadata_index_file()
    data: Dict[str, Any] = {"credentials": []}
    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"credentials": []}

    creds = data.get("credentials", [])
    creds = [c for c in creds if not (c.get("service") == service and c.get("account") == account)]

    if action == "add":
        creds.append({
            "service": service,
            "account": account,
            "updated_at": _get_timestamp(),
        })

    data["credentials"] = creds
    tmp = meta_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, meta_file)


_GLOBAL_STORE: Optional[BaseCredentialStore] = None


def get_credential_store(force_store: Optional[str] = None) -> BaseCredentialStore:
    """Return the platform-appropriate credential store singleton."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is not None and force_store is None:
        return _GLOBAL_STORE

    from desk import config as deskcfg
    store_type = force_store or (deskcfg.get("DESK_CREDENTIAL_STORE") or "").lower()
    if store_type == "memory":
        store = InMemoryCredentialStore()
    elif store_type == "file":
        store = ProtectedFileCredentialStore()
    elif sys.platform == "win32":
        try:
            store = WindowsCredentialStore()
        except Exception:
            store = ProtectedFileCredentialStore()
    elif sys.platform == "darwin":
        store = MacOSCredentialStore()
    else:
        store = ProtectedFileCredentialStore()

    if force_store is None:
        _GLOBAL_STORE = store
    return store
