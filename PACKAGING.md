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

The build command creates an isolated workspace at:

- `build/release-src`

The normal development folder is now the canonical GitHub source tree.
`build/release-src` is only an isolated PyInstaller build workspace.

## Windows release

Run the public build entry point from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The final package is generated under:

- `build/release-src/dist/ResumeDetective`

The script also creates a versioned GitHub Release archive and SHA-256 file:

- `build/release-src/dist/ResumeDetective-vX.Y.Z-windows-x64.zip`
- `build/release-src/dist/ResumeDetective-vX.Y.Z-windows-x64.zip.sha256`

It contains both launch modes:

- `ResumeDetective.exe`: desktop application.
- `ResumeDetectiveGateway.exe`: standalone localhost web dashboard.
- `启动网页看板.bat`: one-click gateway launcher. It prefers the packaged
  gateway EXE and falls back to local Python only in a source checkout.

The gateway listens on `127.0.0.1:8765` by default. The port can be changed
in desktop Settings; both launch modes read the same local configuration.

## Important

- Do not publish your live `data` directory.
- Do not publish your local encrypted key files.
- Do not commit or bundle `Reasonix Cli/reasonix.exe`; users obtain it upstream.
- Do not send only `ResumeDetective.exe` to end users.
- Upload the automatically generated ZIP to GitHub Releases.
- Do not include `screenshots/gateway-*.png`; those files are local QA captures.
