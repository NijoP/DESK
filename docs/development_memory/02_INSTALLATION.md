# 02 — Installation and Environment Setup

This document specifies the verified installation and environment configuration for running Backpass within the DESK development environment.

---

## 1. Environment Verification

Before installing Backpass, verify the host runtime environment in Windows PowerShell:

```powershell
# 1. Verify Node.js version (Required: >= 22.5.0)
node -v
# Verified Host Output: v24.21.0

# 2. Verify npm version
npm -v
# Verified Host Output: 11.19.0

# 3. Verify Git installation
git --version
# Verified Host Output: git version 2.55.0.windows.5

# 4. Check available coding-agent harnesses
claude --version     # Verified: 2.1.316 (Claude Code)
opencode --version   # Verified: 1.18.16 (OpenCode)
```

---

## 2. Production Installation (Windows PowerShell)

Install Backpass and the Agent Communication Protocol eXtension (`acpx`) globally using npm:

```powershell
npm install -g backpass acpx
```

### Post-Installation Verification
Confirm that both executables are resolved on your `PATH`:

```powershell
backpass --version
# Expected: 0.1.44

acpx --version
# Expected: 0.22.0
```

---

## 3. Windows Native Operation & Security Constraints

Backpass runs natively on Windows through Node.js. However, engineers must observe the following platform constraints:

1. **NTFS Security vs. POSIX 0700:**  
   Windows file systems do not support POSIX numeric permissions (`chmod 0700`). Backpass automatically detects `process.platform === 'win32'` and relies on NTFS Access Control Lists (ACLs) inherited from the user profile directory. Avoid redirecting `XDG_CONFIG_HOME` to unencrypted shared network volumes.
2. **Command Interpreter Argument Safety:**  
   When invoking subprocesses, Backpass employs `windowsShimLaunch` to prevent argument pollution in `cmd.exe`. Do not manually construct unquoted wrapper scripts.
3. **Interactive Review Surface:**  
   The optional Lavish web UI (`backpass apply`) requires `lavish-axi`. If not installed, execute the terminal review flow:
   ```powershell
   backpass apply --no-ui
   ```

---

## 4. Alternative WSL2 Setup (Linux Environment)

If developing in an Ubuntu/WSL2 environment, Backpass can be installed inside the Linux container:

```bash
# 1. Ensure Node.js 22.5+ is installed via NodeSource or nvm
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs

# 2. Install Backpass and ACPX globally
sudo npm install -g backpass acpx

# 3. Mount DESK repository
cd /mnt/c/Users/HP/OneDrive/Documents/DESK

# 4. Configure session discovery pointing to Windows host stores if desired
export CLAUDE_CONFIG_DIR="/mnt/c/Users/HP/.claude"
```

> [!NOTE]  
> Operating natively in Windows PowerShell is fully supported and recommended for DESK on this host. WSL2 is optional and not required.
