"""
cli_ai.py — Reasonix CLI 适配层（用户自行安装的可选组件）
不会把 reasonix.exe 打进源码仓库或公开发布包。配置和密钥均落在外置个人
数据目录的 reasonix/，并通过 REASONIX_HOME 指向该目录。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
import tomllib

import requests

from ai_service import desensitize
from paths import REASONIX_CLI_EXE, REASONIX_DATA_DIR, ROOT_DIR


# ── 查找 reasonix.exe（仅限应用目录）──

_REASONIX_CACHE = None


def sanitize_reasonix_output(text: str) -> str:
    """清洗 Reasonix CLI 输出，去掉 ANSI 控制符和思考噪音。"""
    cleaned = text or ""
    cleaned = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(?im)^\s*▎\s*thinking\s*$", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*thinking\s*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _search_reasonix() -> Path | None:
    """查找用户明确配置或放在应用目录中的 reasonix.exe。"""
    candidates = []
    explicit = os.environ.get("REASONIX_CLI_PATH", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    try:
        import config_manager
        configured = config_manager.get_cli_path().strip()
        if configured:
            candidates.append(Path(configured).expanduser())
    except Exception:
        pass
    candidates.extend([
        REASONIX_CLI_EXE,                          # 项目/Reasonix Cli/reasonix.exe
        ROOT_DIR / "reasonix.exe",                 # 项目/reasonix.exe
    ])
    # PyInstaller 打包环境
    if hasattr(sys, "_MEIPASS"):
        mei = Path(sys._MEIPASS)
        candidates.append(mei / "Reasonix Cli" / "reasonix.exe")
        candidates.append(mei / "reasonix.exe")

    for p in candidates:
        if p and p.exists() and p.is_file():
            return p
    return None


def find_reasonix() -> Path | None:
    """返回用户自行安装的 reasonix.exe 路径，None 表示未找到。
    结果会缓存以避免重复搜索。"""
    global _REASONIX_CACHE
    if _REASONIX_CACHE is None:
        _REASONIX_CACHE = _search_reasonix()
    return _REASONIX_CACHE


def get_reasonix_status() -> dict:
    """
    返回可选 Reasonix CLI 的详细状态。
    {
        "found": bool,
        "path": str or None,
        "version": str or None,
        "config_exists": bool,
        "has_provider": bool,
    }
    """
    result = {
        "found": False,
        "path": None,
        "version": None,
        "config_exists": False,
        "has_provider": False,
    }
    exe = find_reasonix()
    if not exe:
        return result
    result["found"] = True
    result["path"] = str(exe)
    # 尝试获取版本
    try:
        r = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
            env=_reasonix_subprocess_env(),
        )
        if r.returncode == 0:
            result["version"] = r.stdout.strip() or r.stderr.strip()
    except Exception:
        pass
    # 检查本地配置
    local_cfg = _get_local_config_path()
    result["config_exists"] = local_cfg.exists()
    if local_cfg.exists():
        result["has_provider"] = _local_config_has_provider(local_cfg)
    return result


def _local_config_has_provider(cfg_path: Path) -> bool:
    """检查本地配置文件中是否有 [[providers]] 定义。"""
    try:
        text = cfg_path.read_text(encoding="utf-8")
        return "[[providers]]" in text
    except Exception:
        return False


# ── 本地 Reasonix 配置管理 ──


def _get_local_config_path() -> Path:
    """返回应用本地 Reasonix config.toml 路径。"""
    return REASONIX_DATA_DIR / "config.toml"


def _get_local_env_path() -> Path:
    """返回应用本地 Reasonix .env 路径。"""
    return REASONIX_DATA_DIR / ".env"


def _get_runtime_root() -> Path:
    """运行时隔离目录，避免会话锁和配置文件被占用。"""
    return REASONIX_DATA_DIR / "runtime"


def _create_runtime_home(api_key: str | None = None) -> Path:
    """
    为单次调用创建隔离的 REASONIX_HOME。
    每次运行都复制一份 config/.env，避免 session 与 config 被别的进程占用。
    """
    ensure_local_reasonix_config(api_key)
    sync_local_reasonix_env(api_key)

    runtime_root = _get_runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_home = runtime_root / f"session-{uuid.uuid4().hex[:12]}"
    runtime_home.mkdir(parents=True, exist_ok=True)

    cfg_src = _get_local_config_path()
    if cfg_src.exists():
        shutil.copy2(cfg_src, runtime_home / "reasonix.toml")
    return runtime_home


def _cleanup_runtime_home(runtime_home: Path | None):
    """清理单次调用的临时运行目录。"""
    if not runtime_home:
        return
    try:
        shutil.rmtree(runtime_home, ignore_errors=True)
    except Exception:
        pass


def _reasonix_subprocess_env(api_key: str | None = None, runtime_home: Path | None = None) -> dict:
    """
    构造 Reasonix 子进程环境。
    - 强制使用外置个人数据目录中的 REASONIX_HOME
    - 若本地 .env 不存在且传入了 api_key，则自动写入
    """
    if api_key is not None:
        sync_local_reasonix_env(api_key)
    env = os.environ.copy()
    env["REASONIX_HOME"] = str(REASONIX_DATA_DIR)
    return env


def get_local_provider_choices() -> dict:
    """
    从应用本地 config.toml 解析 provider 和默认模型。
    返回:
    {
        "default_model": str,
        "providers": [(display, provider_name), ...]
    }
    """
    cfg_path = _get_local_config_path()
    if not cfg_path.exists():
        return {"default_model": "", "providers": []}

    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"default_model": "", "providers": []}

    default_model = (
        data.get("default_model")
        or data.get("reasonix", {}).get("default_model")
        or ""
    )

    provider_entries = []
    seen = set()
    for provider in data.get("providers", []):
        provider_name = (provider.get("name") or "").strip()
        if not provider_name:
            continue
        if provider_name in seen:
            continue
        seen.add(provider_name)
        display = provider_name
        if default_model and provider_name == default_model:
            display = f"{provider_name}（默认）"
        provider_entries.append((display, provider_name))

    return {"default_model": default_model, "providers": provider_entries}


def sync_local_reasonix_env(api_key: str | None = None) -> bool:
    """
    同步外置个人数据目录中的 Reasonix .env。
    若传入 api_key，则写入/覆盖 DEEPSEEK_API_KEY。
    """
    env_path = _get_local_env_path()
    REASONIX_DATA_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []

    mapping = {}
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            mapping[k.strip()] = v

    if api_key:
        mapping["DEEPSEEK_API_KEY"] = api_key
        mapping["REASONIX_API_KEY"] = api_key

    try:
        content = "\n".join(f"{k}={v}" for k, v in mapping.items()).strip()
        if content:
            env_path.write_text(content + "\n", encoding="utf-8")
        elif not env_path.exists():
            env_path.write_text("", encoding="utf-8")
        return True
    except OSError:
        return False


def ensure_local_reasonix_config(api_key: str | None = None) -> bool:
    """如果本地配置文件不存在，生成一份最小 config.toml，并同步本地 .env。"""
    cfg_path = _get_local_config_path()
    REASONIX_DATA_DIR.mkdir(parents=True, exist_ok=True)
    template = """# Reasonix 本地配置（自动生成）
# 自包含目录：通过 REASONIX_HOME 指向外置个人数据目录的 reasonix/

default_model = "deepseek-flash"

[[providers]]
name = "deepseek-flash"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-v4-flash"
api_key_env = "DEEPSEEK_API_KEY"

[[providers]]
name = "deepseek-pro"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-v4-pro"
api_key_env = "DEEPSEEK_API_KEY"

[[providers]]
name = "deepseek-reasoner"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-reasoner"
api_key_env = "DEEPSEEK_API_KEY"

[[providers]]
name = "deepseek-chat"
kind = "openai"
base_url = "https://api.deepseek.com"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
"""
    try:
        should_rewrite = False
        if cfg_path.exists():
            try:
                existing = cfg_path.read_text(encoding="utf-8")
                should_rewrite = ("kind =" not in existing) or ("default_model = \"deepseek/" in existing)
            except OSError:
                should_rewrite = True
        if (not cfg_path.exists()) or should_rewrite:
            cfg_path.write_text(template, encoding="utf-8")
        sync_local_reasonix_env(api_key)
        example_path = REASONIX_DATA_DIR / ".env.example"
        if not example_path.exists():
            example_path.write_text(
                "# Reasonix 环境变量示例\n"
                "# DEEPSEEK_API_KEY=your-api-key-here\n"
                "# REASONIX_API_KEY=your-api-key-here\n",
                encoding="utf-8",
            )
        return True
    except Exception:
        return False


# ── API 模型获取（保持原功能）──


def fetch_deepseek_models(api_key: str) -> list:
    """
    调用 DeepSeek API 获取可用模型列表
    返回 [(显示名, 模型名), ...]
    """
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(10, 30),
        )
        r.raise_for_status()
        data = r.json()
        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if mid:
                models.append((mid, mid))
        return models
    except Exception:
        return []


def get_available_models(api_key: str) -> list:
    """通过 DeepSeek API 获取模型列表。"""
    return fetch_deepseek_models(api_key)


# ── CLI 调用（仅使用应用内副本）──


def call_reasonix_blocking(prompt: str, model: str = None, cli_path: str = None) -> tuple:
    """
    同步调用本地 reasonix CLI。
    返回 (成功?, 回复文本/错误信息)
    cli_path: 可选，显式指定 reasonix.exe 路径
    """
    if cli_path:
        exe = Path(cli_path)
    else:
        exe = find_reasonix()
    if not exe:
        return False, "未找到 Reasonix CLI。请从上游项目自行下载，并放入 Reasonix Cli/ 目录或配置 REASONIX_CLI_PATH。"
    runtime_home = _create_runtime_home()
    cmd = [str(exe), "run"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
            cwd=str(runtime_home),
            env=_reasonix_subprocess_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode == 0:
            output = sanitize_reasonix_output(result.stdout)
            return True, output
        err_text = sanitize_reasonix_output(result.stderr) or f"退出码 {result.returncode}"
        if "this session is in use by another Reasonix window or process" in err_text:
            err_text += "\n\n已自动改为独立会话目录执行；若仍出现该提示，请关闭其它 Reasonix 窗口后重试。"
        return False, err_text
    except subprocess.TimeoutExpired:
        return False, "CLI 调用超时（120秒）"
    except Exception as e:
        return False, str(e)
    finally:
        _cleanup_runtime_home(runtime_home)


def upgrade_reasonix() -> tuple:
    """
    调用用户自行安装的 reasonix upgrade。
    返回 (成功?, 输出文本)
    """
    exe = find_reasonix()
    if not exe:
        return False, "未找到 Reasonix CLI"
    REASONIX_DATA_DIR.mkdir(parents=True, exist_ok=True)
    runtime_home = _create_runtime_home()
    new_exe = exe.parent / ".reasonix.exe.new"
    try:
        result = subprocess.run(
            [str(exe), "upgrade"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
            cwd=str(runtime_home),
            env=_reasonix_subprocess_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode == 0:
            output = sanitize_reasonix_output(result.stdout) or "升级成功"
            return True, output
        if new_exe.exists():
            backup = exe.parent / "reasonix.exe.bak"
            try:
                if backup.exists():
                    backup.unlink()
                for _ in range(6):
                    try:
                        exe.replace(backup)
                        new_exe.replace(exe)
                        break
                    except OSError:
                        time.sleep(0.4)
                else:
                    raise OSError("新内核文件仍被占用，未能完成替换")
                return True, "Reasonix 已完成升级，原文件已备份为 reasonix.exe.bak"
            except OSError as e:
                return False, f"升级包已下载，但替换失败：{e}"
        err = sanitize_reasonix_output(result.stderr) or f"退出码 {result.returncode}"
        return False, err
    except subprocess.TimeoutExpired:
        return False, "更新超时（120秒）"
    except Exception as e:
        return False, str(e)
    finally:
        _cleanup_runtime_home(runtime_home)


def call_reasonix(prompt: str, model: str = None,
                  on_token=None, on_done=None, on_error=None) -> threading.Thread | None:
    """
    在子线程中调用 reasonix run，通过回调返回结果。
    仅使用应用内 CLI 副本。
    """
    exe = find_reasonix()
    if not exe:
        if on_error:
            on_error("未找到 Reasonix CLI。请从上游项目自行下载，并放入 Reasonix Cli/ 目录或配置 REASONIX_CLI_PATH。")
        return None

    cmd = [str(exe), "run"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    def worker():
        runtime_home = None
        try:
            runtime_home = _create_runtime_home()
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=str(runtime_home),
                env=_reasonix_subprocess_env(),
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            for line in iter(proc.stdout.readline, ""):
                if line and on_token:
                    on_token(line)
            proc.stdout.close()
            proc.wait()
            if proc.returncode == 0:
                if on_done:
                    on_done()
            else:
                err = sanitize_reasonix_output(proc.stderr.read() if proc.stderr else "")
                if on_error:
                    on_error(f"退出码 {proc.returncode}: {err[:200]}")
        except FileNotFoundError:
            if on_error:
                on_error("找不到 Reasonix CLI")
        except Exception as e:
            if on_error:
                on_error(str(e))
        finally:
            _cleanup_runtime_home(runtime_home)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


# ── API 直连调用（保持不变）──


def call_deepseek_api_stream(prompt: str, model: str = None,
                              api_key: str = None, system_prompt: str = ""):
    """
    流式调用 DeepSeek API，逐块 yield (text_chunk, is_last)
    用于 UI 逐字显示效果
    """
    key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        yield ("未设置 API Key", True)
        return
    if not model:
        yield ("未选择模型。请先设置 API Key，并点击\u201c刷新模型\u201d获取可用模型。", True)
        return
    safe_prompt = desensitize(prompt)
    safe_system = desensitize(system_prompt) if system_prompt else ""
    messages = []
    if safe_system:
        messages.append({"role": "system", "content": safe_system})
    messages.append({"role": "user", "content": safe_prompt})

    last_error = ""
    try:
        yield from _request_deepseek_stream(messages, model, key)
        return
    except requests.exceptions.Timeout:
        last_error = "请求超时。可能是网络慢、服务端响应慢，或当前模型排队时间过长。"
    except requests.exceptions.HTTPError as e:
        resp = e.response
        detail = ""
        if resp is not None:
            detail = resp.text[:300]
            last_error = f"HTTP {resp.status_code}: {detail}"
        else:
            last_error = str(e)
    except requests.exceptions.RequestException as e:
        last_error = f"网络请求失败：{e}"
    except Exception as e:
        last_error = str(e)
    yield (f"\n\n\u26a0\ufe0f AI 调用失败：{last_error}", True)


def _request_deepseek_stream(messages, model, api_key):
    """执行单次 DeepSeek 流式请求；失败时抛异常给上层做回退。"""
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "stream": True,
        },
        timeout=(10, 180),
        stream=True,
    )
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8", errors="replace")
        if text.startswith("data: "):
            payload = text[6:]
            if payload.strip() == "[DONE]":
                yield ("", True)
                return
            try:
                obj = json.loads(payload)
                delta = obj.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield (content, False)
            except json.JSONDecodeError:
                continue
    yield ("", True)


def call_deepseek_api(prompt: str, model: str = None, api_key: str = None) -> tuple:
    """
    非流式调用 DeepSeek API（一次性返回）
    返回 (成功?, 回复文本/错误信息)
    """
    key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return False, "未设置 API Key"
    if not model:
        return False, "未选择模型"
    safe_prompt = desensitize(prompt)
    try:
        r = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": safe_prompt}],
                "stream": False,
            },
            timeout=(10, 120),
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        return True, content
    except Exception as e:
        return False, f"API 调用失败: {e}"
