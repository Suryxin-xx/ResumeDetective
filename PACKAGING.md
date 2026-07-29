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

- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64.zip`
- `ResumeDetective-Releases/ResumeDetective-vX.Y.Z-windows-x64.zip.sha256`

It contains both launch modes:

- `ResumeDetective.exe`: desktop application.
- `ResumeDetectiveGateway.exe`: standalone localhost web workspace with a
  Windows system-tray controller and no console window.
- `启动网页看板.bat`: one-click silent gateway launcher. It prefers the packaged
  gateway EXE and falls back to `pythonw` only in a source checkout.

The gateway listens on `127.0.0.1:8765` by default. The port can be changed
in desktop Settings; both launch modes read the same local configuration.
The tray menu opens the workspace or exits the background gateway.

## Important

- Do not publish your live `data` directory.
- Do not publish your local encrypted key files.
- Do not commit or bundle `Reasonix Cli/reasonix.exe`; users obtain it upstream.
- Do not send only `ResumeDetective.exe` to end users.
- Upload the automatically generated ZIP to GitHub Releases.
- Do not include `screenshots/gateway-*.png`; those files are local QA captures.
