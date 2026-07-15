# Packaging Notes

## Source release

Use the public EXE entry point:

- `scripts/build_exe.ps1`

It first creates a clean staging tree and then runs PyInstaller from that tree.
The staging step is intentional: it prevents local API keys, databases, resumes,
chat history, Reasonix runtime files, and caches from entering the release.

For source-only packaging, use `scripts/build_release.ps1` directly.

This creates:

- `build/release-src`

That folder is intended to be the clean source snapshot for GitHub.

## Windows release

Run the public build entry point from the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

The final package is generated under:

- `build/release-src/dist/ResumeDetective`

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
- Do not send only `ResumeDetective.exe` to end users.
- Zip the whole `ResumeDetective` output folder before sharing.
- Do not include `screenshots/gateway-*.png`; those files are local QA captures.
