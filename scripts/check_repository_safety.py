"""阻止个人数据、密钥、二进制和本机路径进入 Git 提交。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_PREFIXES = (
    "data/", "reasonix cli/", "build/", "dist/", "release/",
    "local-artifacts/",
)
BLOCKED_EXACT = {".resumedetective.local.json"}
BLOCKED_SUFFIXES = {
    ".db", ".db-shm", ".db-wal", ".enc", ".exe", ".xlsx", ".jsonl",
    ".zip", ".sha256",
}
TEXT_SUFFIXES = {
    ".py", ".ps1", ".bat", ".cmd", ".sh", ".md", ".txt", ".json",
    ".toml", ".yaml", ".yml", ".ini", ".cfg", ".js", ".ts", ".html",
    ".css", ".xml", ".spec", ".example",
}
SECRET_PATTERNS = (
    ("common API key pattern", re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})")),
    ("non-template environment secret", re.compile(r"(?im)^\s*(?:DEEPSEEK_API_KEY|REASONIX_API_KEY)\s*=\s*(?!your-|example|<|\s*$)[^#\s]+")),
    ("plaintext JSON api_key", re.compile(r"(?i)\"api_key\"\s*:\s*\"(?!your-|example|<)[^\"\s]+\"")),
    ("private key material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("machine-specific absolute path", re.compile(r"(?i)(?:[A-Z]:\\Users\\[^\\\r\n]+|E:\\Agent\\Project\\Job)")),
)


def _git_paths(staged: bool) -> list[str] | None:
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"] if staged else [
        "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [item.decode("utf-8", "surrogateescape") for item in result.stdout.split(b"\0") if item]


def _fallback_paths() -> list[str]:
    excluded = {".git", "data", "Reasonix Cli", "build", "dist", "release", "local-artifacts", "__pycache__"}
    result = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in excluded for part in relative.parts):
            continue
        normalized = relative.as_posix()
        if normalized.lower() in BLOCKED_EXACT:
            continue
        result.append(normalized)
    return result


def scan_paths(relative_paths: list[str]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for relative in sorted(set(relative_paths), key=str.lower):
        normalized = relative.replace("\\", "/")
        lowered = normalized.lower()
        path = ROOT / normalized
        if lowered in BLOCKED_EXACT or any(lowered.startswith(prefix) for prefix in BLOCKED_PREFIXES):
            findings.append((normalized, "private/generated path must not be committed"))
            continue
        suffix = "".join(path.suffixes[-2:]).lower() if path.name.lower().endswith((".db-shm", ".db-wal")) else path.suffix.lower()
        if suffix in BLOCKED_SUFFIXES:
            findings.append((normalized, f"blocked generated/sensitive suffix {suffix}"))
            continue
        if path.name.lower() == ".env" or (path.name.lower().endswith(".env") and not path.name.lower().endswith(".env.example")):
            findings.append((normalized, "real .env file"))
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > 20 * 1024 * 1024:
            findings.append((normalized, "file exceeds 20MB"))
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append((normalized, label))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="只检查暂存区文件")
    args = parser.parse_args()
    paths = _git_paths(args.staged)
    if paths is None:
        if args.staged:
            print("[safety] Not a Git repository; staged-file scan is unavailable.", file=sys.stderr)
            return 2
        paths = _fallback_paths()
    findings = scan_paths(paths)
    if findings:
        print("[safety] Refusing publish/commit. Risky paths found (secret values are never printed):", file=sys.stderr)
        for path, reason in findings:
            print(f"  - {path}: {reason}", file=sys.stderr)
        return 1
    print(f"[safety] Passed. Checked {len(paths)} candidate files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
