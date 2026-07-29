# Packaging Notes

## Source release

The development folder is the canonical source repository and can be pushed
directly after `scripts/check_repository_safety.py` passes. Do not copy it to a
second GitHub-only folder.

Use the public EXE entry point:

- `scripts/build_exe.ps1`

It first creates a clean staging tree and then runs PyInstaller from that tree.
The staging step is intentional: it prevents local API keys, databases, resumes,
chat history, Reasonix runtime files, and caches from entering the release.

The build command creates a temporary isolated workspace at:

- `%TEMP%\ResumeDetective-Build`

Pinned build dependencies are cached separately under:

- `%LOCALAPPDATA%\ResumeDetective\BuildEnv`

The cache is keyed by `RUNTIME_VERSION`, Python version, and
`requirements-build.txt`. It is intentionally reused across releases.

The normal development folder is now the canonical GitHub source tree.
The temporary PyInstaller workspace is removed by the public build entry point
after both successful and failed builds.

## Windows release

Run the public build entry point from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The permanent release-only folder is:

- sibling directory `ResumeDetective-Releases`

It contains only versioned GitHub Release archives and SHA-256 files:

- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64-full.zip`
- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64-full.zip.sha256`
- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64-update.zip`
- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64-update.zip.sha256`

The full package contains one executable and two launch modes:

- `ResumeDetective.exe`: desktop application.
- `ResumeDetective.exe --gateway`: standalone localhost web workspace with a
  Windows system-tray controller and no console window.
- `启动网页看板.bat`: one-click silent gateway launcher. It prefers the packaged
  unified EXE and falls back to `pythonw` only in a source checkout.

The update package contains only the executable, launcher, `VERSION`,
`RUNTIME_VERSION`, and `runtime-manifest.json`. It can be applied only when the
installed and update `RUNTIME_VERSION` values match.

The gateway listens on `127.0.0.1:8765` by default. The port can be changed
in desktop Settings; both launch modes read the same local configuration.
Only one gateway process may own a given data directory. Repeated launcher
invocations reuse the address published by the active instance instead of
creating additional background processes.
The tray menu opens the workspace or exits the background gateway.

## Important

- Do not publish your live `data` directory.
- Do not publish your local encrypted key files.
- Do not commit or bundle `Reasonix Cli/reasonix.exe`; users obtain it upstream.
- Do not send only `ResumeDetective.exe` to end users.
- Upload both generated ZIP files and both SHA-256 files to GitHub Releases.
- Do not include `screenshots/gateway-*.png`; those files are local QA captures.
- Bump `RUNTIME_VERSION` whenever Python or a dependency in
  `requirements-build.txt` changes.

## Antivirus and code signing

The public build uses one-folder mode, does not use UPX, and adds a Windows
version resource. These choices reduce heuristic false positives, but an
unsigned executable can still trigger SmartScreen or third-party antivirus.

For public releases, configure one of:

- `RESUMEDETECTIVE_SIGN_SHA1`: certificate thumbprint in the Windows store.
- `RESUMEDETECTIVE_SIGN_PFX` and `RESUMEDETECTIVE_SIGN_PASSWORD`: PFX path and
  password.

An RFC3161 timestamp is added through DigiCert by default. Override it with
`RESUMEDETECTIVE_SIGN_TIMESTAMP`. The build fails if signing was requested but
the resulting signature cannot be verified.
