# Packaging Notes

## Source release

Use:

- `scripts/build_release.ps1`

This creates:

- `build/release-src`

That folder is intended to be the clean source snapshot for GitHub.

## Windows app release

From `build/release-src`, run:

```powershell
pyinstaller ResumeDetective.spec
```

The packaged result will be generated under:

- `build/release-src/dist/ResumeDetective`

## Important

- Do not publish your live `data` directory.
- Do not publish your local encrypted key files.
- Do not send only `ResumeDetective.exe` to end users.
- Zip the whole `ResumeDetective` output folder before sharing.
