# Domain D: Security & OS-Native Authentication Architecture

**Author:** Principal Security Architect & Electronics Platform Engineer  
**Scope:** Zero-Dependency Native OS Credential Storage, Credential Broker, and Agent Secret Isolation  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Architectural Philosophy & Threat Model

In an AI-orchestrated engineering environment, autonomous agents read logs, execute commands, generate reports, and inspect codebases. If raw API credentials (tokens, private keys, client secrets) reside in plaintext files, process arguments, or system environment variables, agents can inadvertently leak them into:
1. LLM context windows and prompts.
2. Chat transcripts and conversation traces.
3. Git commits and unversioned scratch files.
4. Terminal outputs and error stack traces.

### The DESK Security Boundary
DESK enforces a strict, multi-tiered security perimeter:
- **Zero Raw Secrets in Agent Space**: AI agents invoke scoped operations (e.g., `supplier.search`, `manufacturing.quote`). Agents never receive raw API keys.
- **Native OS Vault Integration**: Credentials reside exclusively within the host operating system's native secure credential manager.
- **Zero External Dependencies**: Implemented strictly using Python's standard library (`ctypes`, `subprocess`, `os`, `sys`, `json`, `hashlib`). No third-party packages (`keyring`, `cryptography`, etc.) are permitted.
- **Active Secret Redaction**: The `CredentialBroker` tracks all active secrets and automatically substitutes them with `[REDACTED_SECRET]` across all log outputs, exceptions, and user-facing messages.
- **Fail-Closed Permissions**: Any attempt to access an unconfigured provider halts execution with a structured remediation command.

---

## 2. Platform Storage Implementations

### 2.1 Windows Credential Manager (`WindowsCredentialStore`)
On Windows (`sys.platform == 'win32'`), DESK directly interfaces with the Windows Security Subsystem via `ctypes.windll.advapi32`:
- **API Functions**:
  - `CredWriteW`: Writes credentials with `CRED_TYPE_GENERIC = 1` and `CRED_PERSIST_LOCAL_MACHINE = 2`.
  - `CredReadW`: Retrieves the generic credential blob.
  - `CredFree`: Explicitly releases unmanaged memory allocated by the Windows credential subsystem to prevent heap leaks.
  - `CredDeleteW`: Purges credentials.
- **Target Key Format**: `DESK:{service}:{account}` (e.g. `DESK:lcsc:default`).

### 2.2 macOS Keychain (`MacOSCredentialStore`)
On macOS (`sys.platform == 'darwin'`), DESK communicates with the Apple Keychain via the native `/usr/bin/security` tool:
- `add-generic-password -U -s DESK:{service} -a {account} -w {secret}`
- `find-generic-password -s DESK:{service} -a {account} -w`
- `delete-generic-password -s DESK:{service} -a {account}`

### 2.3 POSIX Protected File Store (`ProtectedFileCredentialStore`)
On Linux and headless POSIX systems where Secret Service DBus may not be available:
- **File Location**: `~/.desk/vault.json`
- **Permissions**: Mode `0600` (`-rw-------`), strictly readable and writable only by the invoking user.
- **Atomic Writes**: Written to a temporary file (`vault.json.tmp`) with mode `0600`, then atomically renamed via `os.replace` to prevent TOCTOU race conditions.
- **Obfuscation**: Salted XOR encoding keyed to the user path to avoid casual plain-text inspection.

### 2.4 Ephemeral Test Store (`InMemoryCredentialStore`)
Provides a sandboxed, in-memory implementation for isolated unit testing, mock CI pipelines, and ephemeral environments where host OS vault mutation is forbidden.

---

## 3. The Credential Broker (`CredentialBroker`)

The `CredentialBroker` acts as an intermediary between client adapters and the storage backend.

```
       ┌────────────────────────┐
       │   AI Agent / LLM      │
       │   (Cannot see secrets) │
       └───────────┬────────────┘
                   │ Calls high-level ops (e.g. 'supplier.search')
                   ▼
       ┌────────────────────────┐
       │  DESK Operation Layer  │
       └───────────┬────────────┘
                   │ Requests authenticated session
                   ▼
       ┌────────────────────────┐
       │   CredentialBroker     │
       │  - Redaction engine    │
       │  - Header minter       │
       │  - Provider health     │
       └─────┬────────────┬─────┘
             │            │
             ▼            ▼
   ┌─────────────────┐  ┌─────────────────────────────┐
   │ Outbound HTTP   │  │ Platform Credential Vault   │
   │ (Injected Auth) │  │ (Windows Credential Mgr,    │
   └─────────────────┘  │  Keychain, or 0600 Vault)   │
                        └─────────────────────────────┘
```

### 3.1 Authenticated Header Generation
Rather than returning secrets, `broker.get_auth_headers(service)` constructs the precise headers required by the vendor:
```python
headers = broker.get_auth_headers("lcsc")
# Returns: {"Authorization": "Bearer <secret>", "Content-Type": "application/json"}
```

### 3.2 Secret Redaction
When errors or raw payloads are processed, `broker.scrub(text)` strips matching secret tokens:
```python
scrubbed_log = broker.scrub("Failed POST request with Bearer secret_token_123")
# Output: "Failed POST request with Bearer [REDACTED_TOKEN]"
```

---

## 4. CLI User Reference

DESK provides an interactive CLI for credential management with hidden password entry via `getpass`:

```bash
# Display configuration status for all ecosystem providers
python tools/desk.py auth status

# Interactively configure credentials (hidden input)
python tools/desk.py auth configure lcsc
python tools/desk.py auth configure jlcpcb
python tools/desk.py auth configure mouser
python tools/desk.py auth configure digikey

# Test provider readiness
python tools/desk.py auth test lcsc

# List configured providers (without exposing secrets)
python tools/desk.py auth list

# Remove credentials
python tools/desk.py auth remove lcsc
```
