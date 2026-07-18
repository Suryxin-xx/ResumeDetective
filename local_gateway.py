"""只监听 localhost 的本地求职工作台，无第三方 Web 框架依赖。"""

from datetime import date, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, quote, urlparse
import mimetypes
import re
import uuid

import config_manager
import db_manager
import file_ops
import paths


HOST, DEFAULT_PORT = "127.0.0.1", 8765
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_RESUME_SUFFIXES = {".pdf", ".doc", ".docx"}
_server = None
_server_port = None


def get_port() -> int:
    return config_manager.get_gateway_port()


def get_url(port=None) -> str:
    return f"http://{HOST}:{port or get_port()}"


def _status_class(status: str) -> str:
    return {"已投递": "blue", "简历初筛": "amber", "笔试/无笔试": "purple", "业务面试": "green", "HR面": "cyan", "Offer": "rose", "终止": "gray"}.get(status, "gray")


def _status_options(current="已投递") -> str:
    return "".join(f'<option value="{escape(item)}" {"selected" if item == current else ""}>{escape(item)}</option>' for item in db_manager.APPLICATION_STATUSES)


def _priority_options(current=0) -> str:
    return "".join(f'<option value="{item}" {"selected" if item == current else ""}>{item}</option>' for item in range(6))


def _display_time(value) -> str:
    """把数据库时间统一成适合表格阅读的分钟精度。"""
    if not value:
        return "未记录"
    return str(value).replace("T", " ")[:16]


def _application_search_text(app: dict) -> str:
    return " ".join(str(app.get(key) or "") for key in (
        "company_name", "position_name", "city", "current_status",
        "application_source", "next_action", "jd_text",
    )).lower()


def _safe_filename(value: str) -> str:
    value = re.sub(r'[^\w\-.]+', '_', value, flags=re.UNICODE).strip('_.')
    return value[:48] or "resume"


def _save_resume_upload(upload: dict | None, company: str, position: str) -> str:
    """保存浏览器上传的简历，返回相对项目根目录的安全路径。"""
    if not upload or not upload.get("content"):
        return ""
    suffix = Path(upload.get("filename", "")).suffix.lower()
    if suffix not in ALLOWED_RESUME_SUFFIXES:
        raise ValueError("简历仅支持 PDF、DOC、DOCX 格式")
    if len(upload["content"]) > MAX_UPLOAD_BYTES:
        raise ValueError("简历文件不能超过 12MB")
    paths.RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{_safe_filename(company)}_{_safe_filename(position)}_{uuid.uuid4().hex[:8]}{suffix}"
    target = paths.RESUMES_DIR / name
    target.write_bytes(upload["content"])
    return paths.stored_data_path(target)


def _absolute_data_path(relative_path: str) -> Path:
    return paths.resolve_data_path(relative_path)


def _safe_resume_path(stored_path: str) -> Path | None:
    """只允许网页读取应用管理的 Resumes 目录，阻止任意本地路径暴露。"""
    if not stored_path:
        return None
    candidate = _absolute_data_path(stored_path).resolve()
    allowed_root = paths.RESUMES_DIR.resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _find_application(app_id: int) -> dict | None:
    return next((app for app in db_manager.get_applications_with_resume() if app["id"] == app_id), None)


def _recycle_application(app_id: int) -> bool:
    """复用桌面端策略：附件、简历先入回收站，再删除数据库投递。"""
    app = _find_application(app_id)
    if not app:
        return False
    for attachment_path in db_manager.delete_attachments_by_application(app_id):
        ok, message = file_ops.recycle_path(_absolute_data_path(attachment_path))
        if not ok:
            print(f"[网页删除附件] {message}: {attachment_path}")
    db_manager.delete_resume(app["resume_id"])
    return True


def _parse_post(handler: BaseHTTPRequestHandler) -> tuple[dict, dict]:
    """解析 urlencoded 和浏览器 multipart 表单；不依赖 Python 3.14 已删除的 cgi 模块。"""
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        raise ValueError("无效的请求长度")
    if length < 0 or length > MAX_UPLOAD_BYTES + 64 * 1024:
        raise ValueError("请求过大")
    raw = handler.rfile.read(length)
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}, {}
    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        raise ValueError("上传请求缺少 boundary")
    boundary = boundary_match.group(1).strip().strip('"').encode("utf-8")
    fields, files = {}, {}
    for chunk in raw.split(b"--" + boundary):
        if not chunk or chunk in (b"--\r\n", b"--"):
            continue
        chunk = chunk.lstrip(b"\r\n")
        try:
            header_raw, value = chunk.split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        value = value.rsplit(b"\r\n", 1)[0]
        headers = header_raw.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', headers)
        if filename_match and filename_match.group(1):
            files[name] = {"filename": Path(filename_match.group(1)).name, "content": value}
        else:
            fields[name] = value.decode("utf-8", "replace")
    return fields, files


UI_ENHANCEMENTS = '''<style>
html{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}button,.btn,input,select,textarea{min-height:42px;font-size:14px;font-weight:500;letter-spacing:.01em;transition:border-color .16s,box-shadow .16s,background .16s,transform .08s}button,.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none;padding:9px 14px}button:active,.btn:active{transform:translateY(1px)}button:focus-visible,.btn:focus-visible,input:focus,select:focus,textarea:focus,summary:focus-visible{outline:none;border-color:#6e97eb;box-shadow:0 0 0 3px rgba(45,104,223,.14)}select{appearance:none;-webkit-appearance:none;padding-right:38px;background-color:#fff;background-image:linear-gradient(45deg,transparent 50%,#52647c 50%),linear-gradient(135deg,#52647c 50%,transparent 50%);background-position:calc(100% - 17px) 18px,calc(100% - 12px) 18px;background-size:5px 5px,5px 5px;background-repeat:no-repeat}input[type=file]{padding:6px 8px;background:#f8faff;border:1px solid #ccd7e6;border-radius:8px;color:#53637a}input[type=file]::file-selector-button{height:29px;border:0;border-radius:6px;background:#e9f0ff;color:#245dc9;font-weight:700;padding:0 11px;margin-right:10px;cursor:pointer}input[type=file]::file-selector-button:hover{background:#dce8ff}.ghost,.filter-chip{background:#edf2fe;color:#275fce;border:1px solid transparent}.filter-chips{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0 16px}.filter-chip{min-height:34px;padding:6px 10px;border-radius:99px;font-size:12px}.filter-chip.active{background:#2d68df;color:#fff}.board-toolbar,.view-switch{display:flex;gap:8px;align-items:center}.board-toolbar input{width:280px}.view-switch{padding:3px;background:#edf1f7;border-radius:10px}.view-switch button{min-height:34px;padding:6px 10px;background:transparent;color:#596a82}.view-switch button.active{background:#fff;color:#235dcc;box-shadow:0 2px 8px rgba(25,37,62,.09)}.board-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:13px;align-items:start}.lane{background:#f7f9fc;border:1px solid #dfe5ee;border-radius:13px;padding:12px;min-width:0}.lane-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.lane-head h3{display:flex;align-items:center;gap:7px}.lane-count{display:inline-flex;align-items:center;justify-content:center;min-width:25px;height:25px;border-radius:99px;background:#e7ecf4;color:#536279;font-size:12px}.lane-body{max-height:430px;overflow-y:auto;padding-right:4px;scrollbar-width:thin}.lane-card{background:#fff;border:1px solid #e3e8f0;border-radius:10px;padding:12px;margin-top:8px;box-shadow:0 3px 10px rgba(25,37,62,.04)}.lane-card:first-child{margin-top:0}.lane-card b{display:block}.lane-card p{margin:5px 0 0;color:#4e5e75;font-size:13px}.lane-card small{display:block;margin-top:8px;color:#66758a;line-height:1.55}.lane-empty{color:#78869a;font-size:12px;padding:12px 3px}.review-form{display:grid;grid-template-columns:1.2fr .8fr 1fr;gap:14px;align-items:end}.review-form .wide{grid-column:1/-1}.review-form button{width:max-content;min-width:135px}.field-file{padding:10px;border:1px dashed #bdcbe0;border-radius:10px;background:#fbfcff}.field-file input{width:100%;margin-top:2px}.results-summary{color:#5f6f86;font-size:12px;margin-left:auto}.table-wrap{width:100%;overflow:auto;border:1px solid #e0e6ef;border-radius:12px;background:#fff}.data-table{width:100%;min-width:890px;border-collapse:collapse;text-align:left}.data-table th{position:sticky;top:0;z-index:1;background:#f5f7fb;color:#52627a;font-size:12px;letter-spacing:.03em;padding:11px 13px;border-bottom:1px solid #dce3ed;white-space:nowrap}.data-table td{padding:12px 13px;border-top:1px solid #e8ecf2;color:#344258;vertical-align:middle}.data-table tbody tr:first-child td{border-top:0}.data-table tbody tr:hover{background:#f8faff}.cell-title{font-weight:750;color:#1c2a40}.cell-sub{display:block;margin-top:3px;color:#66758a;font-size:12px}.cell-action{max-width:240px;white-space:normal}.table-button{min-height:32px;padding:6px 10px;font-size:12px}.quick-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.quick-link{display:block;padding:16px;border:1px solid #dfe6f0;border-radius:12px;background:#fbfcff;color:#1d2d45;text-decoration:none}.quick-link:hover{border-color:#9cb8ef;background:#f3f7ff}.quick-link b{display:block}.quick-link span{display:block;color:#64748a;font-size:12px;margin-top:5px}.manage-panel{margin-top:14px;padding:18px;border:1px solid #b9ccef;border-radius:12px;background:#f9fbff}.manage-panel-head{display:flex;justify-content:space-between;align-items:start;gap:12px;margin-bottom:15px}.manage-panel-head button{min-height:32px}.archive-list{margin-top:14px}.archive-list summary,.create-panel>summary{cursor:pointer;color:#354a68;font-weight:750}.create-panel>summary{padding:2px}.archive-list summary{padding:13px 15px}.archive-list .table-wrap{border-radius:0 0 12px 12px}.archive-shelf{margin-top:14px;border:1px dashed #cbd5e2;border-radius:12px;background:#f8fafc}.archive-shelf>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;padding:13px 15px;color:#4c5c71;font-weight:750}.archive-shelf[open]>summary{border-bottom:1px solid #e1e7ef}.archive-card-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:12px}.review-group{border:1px solid #dfe6ef;border-radius:12px;background:#fff;margin-top:10px;overflow:hidden}.review-group:first-child{margin-top:0}.review-group>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;padding:13px 15px;color:#24344b}.review-group[open]>summary{background:#f7f9fd;border-bottom:1px solid #e4e9f1}.review-group-title{min-width:0}.review-group-count{flex:0 0 auto;color:#52647c;background:#edf2f8;border-radius:99px;padding:4px 8px;font-size:12px}.review-group-body{padding:0 15px}.review-entry{padding:15px 0;border-top:1px solid #e4e9f1}.review-entry:first-child{border-top:0}.review-entry p{white-space:pre-wrap;margin:8px 0 0;color:#435169}.resume-state{font-size:12px;font-weight:700}.ok{color:#14764a}.missing{color:#b04739}.archive-note{color:#6a788b;font-size:12px}.archive-toggle.active{background:#e5ebf4;color:#43536b}.table-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:16px 0 10px}.table-section-title:first-child{margin-top:0}
@media(max-width:700px){.board-toolbar{width:100%;align-items:stretch;flex-direction:column}.board-toolbar input,.board-toolbar>.btn{width:100%}.view-switch{width:100%}.view-switch button{flex:1}.review-form{grid-template-columns:1fr}.review-form .wide{grid-column:auto}.review-form button{width:100%}.filter-chips{gap:5px}.filter-chip{flex:1 0 auto}.quick-grid,.archive-card-grid{grid-template-columns:1fr}.manage-panel-head{flex-direction:column}.data-table{min-width:780px}.review-group>summary{align-items:flex-start}.table-section-title{align-items:flex-start;flex-direction:column}}
</style>'''

ARCHIVE_STYLES = '''<style>
.archive{grid-column:1/-1;border:1px solid #e1e7f0;border-radius:10px;background:#fafbfe;overflow:hidden}.archive summary{cursor:pointer;padding:10px 12px;color:#3e5069;font-weight:700}.archive-fields{display:grid;grid-template-columns:1fr 1.4fr;gap:10px;padding:0 12px 12px}.archive-fields .full{grid-column:1/-1}.archive-fields textarea{min-height:130px}.add-form .full{grid-column:1/-1}.source-note{color:#768397;font-size:11px;margin-top:5px}.job-link{color:#2864d2;text-decoration:none;word-break:break-all}.job-link:hover{text-decoration:underline}
@media(max-width:700px){.archive-fields{grid-template-columns:1fr}.archive-fields .full,.add-form .full{grid-column:auto}}
</style>'''


def _layout(title: str, current: str, body: str, port: int) -> str:
    nav = f'''<nav><a class="{"active" if current == "overview" else ""}" href="/">总览</a><a class="{"active" if current == "board" else ""}" href="/board">状态看板</a><a class="{"active" if current == "applications" else ""}" href="/applications">投递管理</a><a class="{"active" if current == "interviews" else ""}" href="/interviews">面试复盘</a><a class="{"active" if current == "resumes" else ""}" href="/resumes">简历汇总</a></nav>'''
    body = UI_ENHANCEMENTS + ARCHIVE_STYLES + body
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · Resume Detective</title><style>
    :root{{--bg:#f5f7fb;--paper:#fff;--ink:#182235;--muted:#64748a;--line:#e1e7f0;--brand:#2d68df;--danger:#cb3a46;--shadow:0 8px 26px rgba(25,37,62,.07)}}*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Segoe UI","Microsoft YaHei UI","Microsoft YaHei","PingFang SC",sans-serif}}.shell{{width:100%;max-width:1280px;margin:auto;padding:0 20px 50px}}header{{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:24px 0 17px;border-bottom:1px solid var(--line)}}h1{{margin:0;font-size:23px;letter-spacing:-.01em}}.local{{font-size:12px;font-weight:700;color:#187546;background:#e7f8ee;padding:7px 10px;border-radius:99px;white-space:nowrap}}nav{{display:flex;flex-wrap:wrap;gap:6px;padding:15px 0}}nav a{{text-decoration:none;color:#4f6078;padding:8px 12px;border-radius:8px;font-weight:700}}nav a:hover{{background:#eaf0ff;color:#235bcd}}nav a.active{{background:#2d68df;color:#fff}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:2px 0 16px}}.stat,.panel{{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}}.stat{{padding:15px 17px}}.stat span,.hint{{color:var(--muted);font-size:12px}}.stat b{{display:block;font-size:25px;margin-top:5px}}.stat.primary{{background:linear-gradient(130deg,#2b66dd,#6793ec);border:0;color:#fff}}.stat.primary span{{color:#dfeaff}}.panel{{padding:20px;margin-bottom:16px}}.panel-head{{display:flex;justify-content:space-between;gap:15px;align-items:start;margin-bottom:16px}}h2{{margin:0 0 5px;font-size:18px}}h3{{margin:0;font-size:16px}}.grid-two{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}form{{margin:0}}label{{display:grid;gap:7px;color:#43536b;font-size:13px;font-weight:750}}input,select,textarea,button{{font-family:inherit;border-radius:8px;padding:9px 10px}}input,select,textarea{{border:1px solid #ccd6e4;background:#fff;color:#1c2a40;min-width:0}}textarea{{min-height:96px;resize:vertical;line-height:1.55}}button{{border:0;background:var(--brand);color:#fff;font-weight:700;cursor:pointer}}button:hover{{background:#1e57ca}}button.danger{{background:#fff0f1;color:var(--danger)}}button.danger:hover{{background:#ffe3e5}}.add-form{{display:grid;grid-template-columns:1fr 1.15fr .75fr .8fr .55fr;gap:12px;align-items:end}}.add-form .wide{{grid-column:span 2}}.add-form .file{{grid-column:span 2}}.add-form button{{height:42px}}.toolbar{{display:flex;gap:8px;align-items:center}}.toolbar input{{width:280px}}.ghost{{background:#edf2fe;color:#275fce}}.badge{{padding:5px 8px;border-radius:7px;font-size:12px;font-weight:700;white-space:nowrap}}.blue{{background:#e9f1ff;color:#245fd4}}.amber{{background:#fff1dc;color:#a85b08}}.purple{{background:#f1eaff;color:#7441b5}}.green{{background:#e3f7ec;color:#197c4b}}.cyan{{background:#dff5f8;color:#176b7b}}.rose{{background:#ffe7ee;color:#a62f54}}.gray{{background:#eef1f5;color:#5f6d80}}.manage-form{{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:end}}.manage-form .wide{{grid-column:1/-1}}.resume-row{{display:flex;gap:10px;align-items:center;padding:11px;border:1px dashed #bdcbe0;border-radius:9px;grid-column:1/-1}}.resume-row input{{padding:0;border:0;flex:1;max-width:100%}}.resume-row a{{font-size:12px;color:#2460d0;white-space:nowrap}}.actions{{display:flex;gap:8px;grid-column:1/-1}}.actions button{{flex:1}}.todo,.reviews{{list-style:none;padding:0;margin:0}}.todo li,.review{{padding:11px 0;border-top:1px solid var(--line);line-height:1.5}}.todo li:first-child,.review:first-child{{border-top:0;padding-top:0}}time{{font-size:12px;color:#52647c;display:inline-block;min-width:90px}}time.overdue{{color:#be3740}}.next-list{{display:grid;gap:10px}}.next-item{{border:1px solid var(--line);border-radius:10px;padding:12px}}.next-item b{{display:block}}.next-item p{{margin:5px 0 0;color:#48566c}}.empty{{margin:0;color:var(--muted);line-height:1.6}}.hidden{{display:none!important}}@media(max-width:850px){{.add-form{{grid-template-columns:1fr 1fr}}.add-form .wide,.add-form .file{{grid-column:auto}}.add-form button{{grid-column:1/-1}}.grid-two{{grid-template-columns:1fr}}}}@media(max-width:580px){{.shell{{padding:0 13px 36px}}header{{align-items:flex-start;flex-direction:column}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}.panel{{padding:16px}}.panel-head{{flex-direction:column}}.toolbar{{width:100%;flex-direction:column;align-items:stretch}}.toolbar input{{width:100%}}.add-form,.manage-form{{grid-template-columns:1fr}}.add-form .wide,.add-form .file,.manage-form .wide{{grid-column:auto}}.resume-row{{grid-column:auto;align-items:start;flex-direction:column}}.actions{{grid-column:auto;flex-direction:column}}}}</style></head><body><main class="shell"><header><h1>秋招工作台</h1><div class="local">仅本机访问 · 127.0.0.1:{port}</div></header>{nav}{body}</main></body></html>'''


def _overview_page(port: int) -> str:
    apps, tasks = db_manager.get_applications_with_resume(), db_manager.get_job_tasks("open")
    active = [item for item in apps if item["current_status"] not in ("Offer", "终止")]
    today, week = date.today().isoformat(), (date.today() + timedelta(days=7)).isoformat()
    upcoming = [item for item in tasks if item.get("due_date") and item["due_date"] <= week][:8]
    next_actions = [item for item in active if item.get("next_action")][:8]
    todo_html = "".join(f'<li><time class="{"overdue" if item["due_date"] < today else ""}">{escape(item["due_date"])}</time>{escape(item["title"])}</li>' for item in upcoming) or '<li class="empty">未来 7 天没有已安排待办。</li>'
    next_html = "".join(f'<article class="next-item"><b>{escape(item["company_name"])} · {escape(item["position_name"])}</b><p>{escape(item["next_action"])}</p></article>' for item in next_actions) or '<p class="empty">流程中岗位暂未填写下一步行动。</p>'
    body = f'''<section class="stats"><div class="stat primary"><span>全部投递</span><b>{len(apps)}</b></div><div class="stat"><span>流程中</span><b>{len(active)}</b></div><div class="stat"><span>面试阶段</span><b>{sum(item["current_status"] in ("业务面试", "HR面") for item in apps)}</b></div><div class="stat"><span>Offer</span><b>{sum(item["current_status"] == "Offer" for item in apps)}</b></div></section>
    <div class="grid-two"><section class="panel"><div class="panel-head"><div><h2>近期待办</h2><div class="hint">未来 7 天内的行动清单</div></div></div><ul class="todo">{todo_html}</ul></section><section class="panel"><div class="panel-head"><div><h2>流程中的下一步</h2><div class="hint">来自岗位投递记录</div></div></div><div class="next-list">{next_html}</div></section></div><section class="panel"><div class="panel-head"><div><h2>快速进入工作区</h2><div class="hint">总览只保留今天真正需要关注的信息。</div></div></div><div class="quick-grid"><a class="quick-link" href="/applications"><b>管理投递</b><span>搜索、筛选并只展开当前要修改的岗位</span></a><a class="quick-link" href="/interviews"><b>记录面试复盘</b><span>独立记录每轮问题、表现与补强点</span></a><a class="quick-link" href="/resumes"><b>查看关联简历</b><span>集中检查每条投递绑定了哪个版本</span></a></div></section>'''
    return _layout("总览", "overview", body, port)


def _board_page(port: int) -> str:
    """活跃流程优先；终止岗位在看板归档，在表格中按需显示。"""
    apps = db_manager.get_applications_with_resume()
    active_apps = [app for app in apps if app["current_status"] != "终止"]
    terminated_apps = [app for app in apps if app["current_status"] == "终止"]
    lanes = []
    for status in (item for item in db_manager.APPLICATION_STATUSES if item != "终止"):
        status_apps = [item for item in active_apps if item["current_status"] == status]
        cards = "".join(
            f'''<article class="lane-card" data-search="{escape(_application_search_text(item))}"><b>{escape(item["company_name"])}</b><p>{escape(item["position_name"])} · {escape(item.get("city") or "地点未填")}</p><small>来源：{escape(item.get("application_source") or "未记录")}<br>下一步：{escape(item.get("next_action") or "暂未填写")}<br>状态更新：{escape(_display_time(item.get("status_update_time")))}</small></article>'''
            for item in status_apps
        ) or '<div class="lane-empty">暂无岗位</div>'
        lanes.append(f'''<section class="lane"><div class="lane-head"><h3><span class="badge {_status_class(status)}">{escape(status)}</span></h3><span class="lane-count">{len(status_apps)}</span></div><div class="lane-body">{cards}</div></section>''')
    archive_cards = "".join(
        f'''<article class="lane-card archived-card" data-search="{escape(_application_search_text(app))}"><b>{escape(app["company_name"])}</b><p>{escape(app["position_name"])} · {escape(app.get("city") or "地点未填")}</p><small>来源：{escape(app.get("application_source") or "未记录")}<br>终止时间：{escape(_display_time(app.get("status_update_time")))}</small></article>'''
        for app in terminated_apps
    ) or '<p class="empty">暂无终止岗位。</p>'
    rows = []
    for app in apps:
        archived = app["current_status"] == "终止"
        action = '<a class="btn ghost table-button" href="/applications">查看归档</a>' if archived else f'<a class="btn ghost table-button" href="/applications#app-{app["id"]}">管理</a>'
        rows.append(f'''<tr class="{"archived-row hidden" if archived else ""}" data-archived="{"1" if archived else "0"}" data-search="{escape(_application_search_text(app))}"><td><span class="cell-title">{escape(app["company_name"])}</span><span class="cell-sub">{escape(app["position_name"])}</span></td><td><span class="badge {_status_class(app["current_status"])}">{escape(app["current_status"])}</span></td><td>{escape(app.get("city") or "未填")}</td><td>{escape(app.get("application_source") or "未记录")}</td><td class="cell-action">{escape(app.get("next_action") or "—")}</td><td>{escape(_display_time(app.get("status_update_time")))}</td><td>{action}</td></tr>''')
    body = f'''<section class="panel"><div class="panel-head"><div><h2>投递状态</h2><div class="hint">先看仍需推进的岗位；已终止记录保留在历史档案中。</div></div><div class="board-toolbar"><input id="boardSearch" placeholder="搜索公司、岗位、地点、来源或下一步"><div class="view-switch"><button type="button" class="active" data-view="board">看板</button><button type="button" data-view="table">表格</button></div><button type="button" class="ghost archive-toggle table-only hidden" id="toggleTerminated">显示终止 · {len(terminated_apps)}</button><a class="btn ghost" href="/applications">管理投递</a></div></div><div id="boardView"><div class="board-grid">{''.join(lanes)}</div><details class="archive-shelf" id="boardArchive"><summary><span>已终止岗位 · {len(terminated_apps)}</span><span class="archive-note">历史档案，不参与当前流程</span></summary><div class="archive-card-grid">{archive_cards}</div></details></div><div class="table-wrap hidden" id="tableView"><table class="data-table"><thead><tr><th>公司 / 岗位</th><th>状态</th><th>地点</th><th>来源</th><th>下一步</th><th>状态更新时间</th><th>操作</th></tr></thead><tbody id="boardTableRows">{''.join(rows)}<tr id="boardEmpty" class="hidden"><td colspan="7" class="empty">没有匹配的岗位。</td></tr></tbody></table></div></section><script>const search=document.querySelector('#boardSearch'),board=document.querySelector('#boardView'),table=document.querySelector('#tableView'),archive=document.querySelector('#boardArchive'),toggle=document.querySelector('#toggleTerminated'),switches=document.querySelectorAll('[data-view]');let includeTerminated=false;function setView(view){{localStorage.setItem('rd-board-view',view);board.classList.toggle('hidden',view!=='board');table.classList.toggle('hidden',view!=='table');toggle.classList.toggle('hidden',view!=='table');switches.forEach(b=>b.classList.toggle('active',b.dataset.view===view));applyFilters()}}switches.forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));toggle.addEventListener('click',()=>{{includeTerminated=!includeTerminated;toggle.classList.toggle('active',includeTerminated);toggle.textContent=(includeTerminated?'隐藏终止 · ':'显示终止 · ')+{len(terminated_apps)};applyFilters()}});function applyFilters(){{const q=search.value.toLowerCase();document.querySelectorAll('#boardView .lane-card[data-search]').forEach(card=>card.classList.toggle('hidden',q&&!card.dataset.search.includes(q)));document.querySelectorAll('.lane').forEach(lane=>{{const visible=[...lane.querySelectorAll('.lane-card')].some(card=>!card.classList.contains('hidden'));lane.classList.toggle('hidden',q&&!visible)}});const archivedCards=[...archive.querySelectorAll('.archived-card[data-search]')],archiveMatch=archivedCards.some(card=>!card.classList.contains('hidden'));archive.classList.toggle('hidden',q&&!archiveMatch);if(q&&archiveMatch)archive.open=true;let visibleRows=0;document.querySelectorAll('#boardTableRows tr[data-search]').forEach(row=>{{const show=(!q||row.dataset.search.includes(q))&&(includeTerminated||row.dataset.archived!=='1');row.classList.toggle('hidden',!show);if(show)visibleRows++}});document.querySelector('#boardEmpty').classList.toggle('hidden',visibleRows!==0)}}search.addEventListener('input',applyFilters);setView(localStorage.getItem('rd-board-view')||'board');</script>'''
    return _layout("状态看板", "board", body, port)


def _applications_page(port: int) -> str:
    apps = db_manager.get_applications_with_resume()
    active_apps = [app for app in apps if app["current_status"] != "终止"]
    terminated_apps = [app for app in apps if app["current_status"] == "终止"]
    rows, editors = [], []
    for app in active_apps:
        app_id, priority = app["id"], int(app.get("priority") or 0)
        resume_name = Path(app.get("file_path") or "").name or "尚未绑定简历"
        resume_link = f'<a href="/resume/{app_id}" target="_blank">查看简历</a>' if _safe_resume_path(app.get("file_path") or "") else ""
        job_link_view = f'<a class="job-link" href="{escape(app.get("job_link") or "")}" target="_blank" rel="noopener noreferrer">打开原岗位页面</a>' if app.get("job_link") else '<span class="hint">未记录岗位链接</span>'
        rows.append(f'''<tr id="app-{app_id}" data-status="{escape(app["current_status"])}" data-search="{escape(_application_search_text(app))}"><td><span class="cell-title">{escape(app["company_name"])}</span><span class="cell-sub">{escape(app["position_name"])}</span></td><td><span class="badge {_status_class(app["current_status"])}">{escape(app["current_status"])}</span></td><td>{escape(app.get("city") or "未填")}</td><td>{escape(app.get("application_source") or "未记录")}</td><td class="cell-action">{escape(app.get("next_action") or "暂未填写")}</td><td>{escape(_display_time(app.get("status_update_time")))}</td><td><button type="button" class="table-button" data-open-app="{app_id}">管理</button></td></tr>''')
        editors.append(f'''<section class="manage-panel hidden" id="editor-{app_id}"><div class="manage-panel-head"><div><h3>{escape(app["company_name"])} · {escape(app["position_name"])}</h3><div class="hint">状态最后更新：{escape(_display_time(app.get("status_update_time")))}</div></div><button type="button" class="ghost" data-close-editor>收起</button></div><form class="manage-form" method="post" action="/application/{app_id}" enctype="multipart/form-data"><input type="hidden" name="previous_status" value="{escape(app["current_status"])}"><label>更新状态<select name="status">{_status_options(app["current_status"])}</select></label><label>优先级<select name="priority">{_priority_options(priority)}</select></label><label class="wide">下一步行动<input name="next_action" value="{escape(app.get("next_action") or "")}" placeholder="例如：准备一面"></label><details class="archive"><summary>投递来源与 JD 存档</summary><div class="archive-fields"><label>投递来源<input name="application_source" value="{escape(app.get("application_source") or "")}" placeholder="官网 / 内推 / 牛客 / 招聘群"></label><label>岗位原始链接<input name="job_link" type="url" value="{escape(app.get("job_link") or "")}" placeholder="https://..."></label><div class="full">{job_link_view}</div><label class="full">JD 原文快照<textarea name="jd_text" placeholder="粘贴完整 JD，岗位关闭后仍可复盘">{escape(app.get("jd_text") or "")}</textarea></label></div></details><div class="resume-row field-file"><div><b>关联简历</b><div class="hint">{escape(resume_name)}</div></div>{resume_link}<input type="file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"><span class="hint">选择文件后保存即可绑定或替换</span></div><div class="actions"><button>保存修改</button><button formmethod="post" formaction="/application/{app_id}/delete" class="danger" onclick="return confirm('确认删除这条投递吗？关联简历和附件会移入系统回收站。');">删除投递</button></div></form></section>''')
    active_rows = "".join(rows) or '<tr><td colspan="7" class="empty">暂无流程中的投递。</td></tr>'
    archive_rows = "".join(f'''<tr><td><span class="cell-title">{escape(app["company_name"])}</span><span class="cell-sub">{escape(app["position_name"])}</span></td><td>{escape(app.get("application_source") or "未记录")}</td><td>{escape(_display_time(app.get("status_update_time")))}</td><td><form method="post" action="/application/{app['id']}/reopen"><button class="ghost table-button">恢复跟踪</button></form></td></tr>''' for app in terminated_apps) or '<tr><td colspan="4" class="empty">暂无终止岗位。</td></tr>'
    active_statuses = [status for status in db_manager.APPLICATION_STATUSES if status != "终止"]
    status_counts = {status: sum(app["current_status"] == status for app in active_apps) for status in active_statuses}
    filter_html = '<button type="button" class="filter-chip active" data-status="">全部 · %d</button>' % len(active_apps) + "".join(f'<button type="button" class="filter-chip" data-status="{escape(status)}">{escape(status)} · {status_counts[status]}</button>' for status in active_statuses)
    body = f'''<section class="panel"><details class="create-panel"><summary>＋ 新增投递</summary><div class="hint" style="margin:8px 0 16px">保存来源、链接和 JD 快照，即使岗位关闭也能复盘。</div><form class="add-form" method="post" action="/application" enctype="multipart/form-data"><label>公司名称<input required name="company_name" placeholder="例如：字节跳动"></label><label>岗位名称<input required name="position_name" placeholder="例如：后端开发工程师"></label><label>工作地点<input name="city" placeholder="北京"></label><label>当前状态<select name="status">{_status_options()}</select></label><label>优先级<select name="priority">{_priority_options()}</select></label><label class="wide">下一步行动<input name="next_action" placeholder="例如：完成网申、准备笔试"></label><label>投递来源<input name="application_source" placeholder="官网 / 内推 / 牛客"></label><label class="wide">岗位原始链接<input name="job_link" type="url" placeholder="https://..."></label><label class="full">JD 原文快照<textarea name="jd_text" placeholder="粘贴完整岗位描述，便于后期复盘"></textarea></label><label class="file field-file">关联本地简历（可选）<input type="file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"></label><button>添加投递</button></form></details></section>
    <section class="panel"><div class="panel-head"><div><h2>投递管理</h2><div class="hint">终止岗位已移出主列表；点击“管理”时只展开一条记录。</div></div><div class="toolbar"><input id="search" placeholder="搜索公司、岗位、地点、来源或 JD"><span class="results-summary" id="resultsSummary"></span></div></div><div class="filter-chips">{filter_html}</div><div class="table-wrap"><table class="data-table"><thead><tr><th>公司 / 岗位</th><th>状态</th><th>地点</th><th>来源</th><th>下一步</th><th>状态更新时间</th><th>操作</th></tr></thead><tbody id="applicationRows">{active_rows}</tbody></table></div>{''.join(editors)}<details class="archive-list"><summary>已终止岗位 · {len(terminated_apps)}</summary><div class="table-wrap"><table class="data-table"><thead><tr><th>公司 / 岗位</th><th>来源</th><th>终止时间</th><th>操作</th></tr></thead><tbody>{archive_rows}</tbody></table></div></details></section><script>const search=document.querySelector('#search'),summary=document.querySelector('#resultsSummary');let selectedStatus='';function applyFilters(){{const q=search.value.toLowerCase();let visible=0;document.querySelectorAll('#applicationRows tr[data-search]').forEach(row=>{{const show=(!q||row.dataset.search.includes(q))&&(!selectedStatus||row.dataset.status===selectedStatus);row.classList.toggle('hidden',!show);if(show)visible++}});summary.textContent='显示 '+visible+' 条'}}search.addEventListener('input',applyFilters);document.querySelectorAll('.filter-chip').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.filter-chip').forEach(item=>item.classList.remove('active'));button.classList.add('active');selectedStatus=button.dataset.status;applyFilters()}}));function closeEditors(){{document.querySelectorAll('.manage-panel').forEach(panel=>panel.classList.add('hidden'))}}document.querySelectorAll('[data-open-app]').forEach(button=>button.addEventListener('click',()=>{{closeEditors();const panel=document.querySelector('#editor-'+button.dataset.openApp);if(panel){{panel.classList.remove('hidden');panel.scrollIntoView({{behavior:'smooth',block:'center'}})}}}}));document.querySelectorAll('[data-close-editor]').forEach(button=>button.addEventListener('click',closeEditors));const hash=location.hash.match(/^#app-(\\d+)$/);if(hash){{const button=document.querySelector('[data-open-app="'+hash[1]+'"]');if(button)button.click()}}applyFilters();</script>'''
    return _layout("投递管理", "applications", body, port)


def _interviews_page(port: int) -> str:
    apps = [app for app in db_manager.get_applications_with_resume() if app["current_status"] != "终止"]
    interviews = db_manager.get_interviews()
    options = "".join(f'<option value="{app["id"]}">{escape(app["company_name"])} · {escape(app["position_name"])}</option>' for app in apps)
    grouped = {}
    for item in interviews:
        key = item.get("application_id") or (item.get("company_name"), item.get("position_name"))
        grouped.setdefault(key, []).append(item)
    group_html = []
    for index, group in enumerate(grouped.values()):
        first = group[0]
        search_text = " ".join(
            f'{item.get("company_name") or ""} {item.get("position_name") or ""} {item.get("round") or ""} {item.get("summary") or ""}'
            for item in group
        ).lower()
        entries = "".join(f'''<article class="review-entry"><b><span class="badge green">{escape(item.get("round") or "其他")}</span></b><span class="cell-sub">{escape(_display_time(item.get("interview_time")))}</span><p>{escape(item.get("summary") or "未填写复盘内容")}</p></article>''' for item in group)
        group_html.append(f'''<details class="review-group" data-search="{escape(search_text)}" {"open" if index == 0 else ""}><summary><span class="review-group-title"><b>{escape(first.get("company_name") or "未命名公司")} · {escape(first.get("position_name") or "未命名岗位")}</b><span class="cell-sub">最近记录：{escape(_display_time(first.get("interview_time")))}</span></span><span class="review-group-count">{len(group)} 轮</span></summary><div class="review-group-body">{entries}</div></details>''')
    groups = "".join(group_html) or '<p class="empty">暂无面试复盘。完成一次面试后，可以在上方记录问题和补强点。</p>'
    form = f'''<form class="review-form" method="post" action="/interview"><label>对应岗位<select name="application_id" required>{options}</select></label><label>面试轮次<select name="round"><option>一面</option><option>二面</option><option>三面</option><option>HR 面</option><option>其他</option></select></label><label>面试时间<input name="interview_time" type="datetime-local"></label><label class="wide">复盘内容<textarea name="summary" placeholder="记录主要问题、没答好的内容、复盘结论和后续补强点"></textarea></label><button {"disabled" if not apps else ""}>保存面试复盘</button></form>'''
    body = f'''<section class="panel"><div class="panel-head"><div><h2>新增面试复盘</h2><div class="hint">一条记录对应一轮面试；已终止岗位不会出现在新增记录的下拉选项中。</div></div></div>{form}</section><section class="panel"><div class="panel-head"><div><h2>历史复盘</h2><div class="hint">{len(grouped)} 个岗位 · {len(interviews)} 轮面试；终止岗位的经验仍会保留。</div></div><div class="toolbar"><input id="reviewSearch" placeholder="搜索公司、岗位、轮次或复盘内容"></div></div><div id="reviews">{groups}</div></section><script>const reviewSearch=document.querySelector('#reviewSearch'),reviewGroups=[...document.querySelectorAll('.review-group[data-search]')];reviewSearch.addEventListener('input',()=>{{const q=reviewSearch.value.toLowerCase();reviewGroups.forEach((group,index)=>{{const show=!q||group.dataset.search.includes(q);group.classList.toggle('hidden',!show);if(q&&show)group.open=true;else if(!q)group.open=index===0}})}});</script>'''
    return _layout("面试复盘", "interviews", body, port)


def _resumes_page(port: int) -> str:
    apps = db_manager.get_applications_with_resume()
    current_apps = [app for app in apps if app["current_status"] != "终止"]
    historical_apps = [app for app in apps if app["current_status"] == "终止"]

    def build_row(app, archived=False):
        file_path = app.get("file_path") or ""
        safe_path = _safe_resume_path(file_path)
        if safe_path:
            state = '<span class="resume-state ok">可查看</span>'
            action = f'<a class="btn ghost table-button" href="/resume/{app["id"]}" target="_blank">打开简历</a>'
        elif file_path:
            state = '<span class="resume-state missing">文件缺失</span>'
            action = '<span class="archive-note">历史记录</span>' if archived else '<a class="btn ghost table-button" href="/applications#app-%s">重新绑定</a>' % app["id"]
        else:
            state = '<span class="resume-state missing">未绑定</span>'
            action = '<span class="archive-note">无需处理</span>' if archived else '<a class="btn ghost table-button" href="/applications#app-%s">去绑定</a>' % app["id"]
        filename = Path(file_path).name if file_path else "—"
        return f'''<tr data-search="{escape(_application_search_text(app)+' '+filename.lower())}"><td><span class="cell-title">{escape(app["company_name"])}</span><span class="cell-sub">{escape(app["position_name"])}</span></td><td>{escape(filename)}</td><td>{state}</td><td><span class="badge {_status_class(app["current_status"])}">{escape(app["current_status"])}</span></td><td>{escape(_display_time(app.get("upload_time")))}</td><td>{escape(_display_time(app.get("status_update_time")))}</td><td>{action}</td></tr>'''

    current_rows = "".join(build_row(app) for app in current_apps) or '<tr><td colspan="7" class="empty">暂无当前投递记录。</td></tr>'
    historical_rows = "".join(build_row(app, archived=True) for app in historical_apps) or '<tr><td colspan="7" class="empty">暂无历史关联简历。</td></tr>'
    current_bound = sum(bool(_safe_resume_path(app.get("file_path") or "")) for app in current_apps)
    body = f'''<section class="stats"><div class="stat primary"><span>当前投递</span><b>{len(current_apps)}</b></div><div class="stat"><span>当前已关联</span><b>{current_bound}</b></div><div class="stat"><span>当前待绑定 / 缺失</span><b>{len(current_apps)-current_bound}</b></div><div class="stat"><span>历史记录</span><b>{len(historical_apps)}</b></div></section><section class="panel"><div class="panel-head"><div><h2>关联简历汇总</h2><div class="hint">优先检查仍在推进的岗位；终止岗位使用过的简历保留在历史区。</div></div><div class="toolbar"><input id="resumeSearch" placeholder="搜索公司、岗位或文件名"><span class="results-summary" id="resumeSummary"></span></div></div><div class="table-section-title"><div><h3>当前投递关联简历</h3><div class="hint">{len(current_apps)} 条需要继续关注的投递</div></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>公司 / 岗位</th><th>简历文件</th><th>文件状态</th><th>投递状态</th><th>记录时间</th><th>状态更新时间</th><th>操作</th></tr></thead><tbody id="currentResumeRows">{current_rows}</tbody></table></div><details class="archive-shelf" id="resumeArchive"><summary><span>历史关联简历 · {len(historical_apps)}</span><span class="archive-note">来自已终止岗位，保留用于版本复盘</span></summary><div class="table-wrap" style="border:0;border-radius:0 0 12px 12px"><table class="data-table"><thead><tr><th>公司 / 岗位</th><th>简历文件</th><th>文件状态</th><th>投递状态</th><th>记录时间</th><th>状态更新时间</th><th>操作</th></tr></thead><tbody id="historicalResumeRows">{historical_rows}</tbody></table></div></details></section><script>const resumeSearch=document.querySelector('#resumeSearch'),summary=document.querySelector('#resumeSummary'),resumeArchive=document.querySelector('#resumeArchive');function filterResumes(){{const q=resumeSearch.value.toLowerCase();let current=0,history=0;document.querySelectorAll('#currentResumeRows tr[data-search]').forEach(row=>{{const show=!q||row.dataset.search.includes(q);row.classList.toggle('hidden',!show);if(show)current++}});document.querySelectorAll('#historicalResumeRows tr[data-search]').forEach(row=>{{const show=!q||row.dataset.search.includes(q);row.classList.toggle('hidden',!show);if(show)history++}});resumeArchive.classList.toggle('hidden',q&&history===0);if(q&&history)resumeArchive.open=true;summary.textContent='当前 '+current+' · 历史 '+history}}resumeSearch.addEventListener('input',filterResumes);filterResumes();</script>'''
    return _layout("简历汇总", "resumes", body, port)


def _resume_response(handler: BaseHTTPRequestHandler, app_id: int, *, send_body=True):
    app = _find_application(app_id)
    if not app or not app.get("file_path"):
        handler._send_problem(404, "未绑定简历"); return
    file_path = _safe_resume_path(app["file_path"])
    if file_path is None:
        handler._send_problem(404, "简历文件不存在"); return
    total_size = file_path.stat().st_size
    start, end, status_code = 0, total_size - 1, 200
    range_header = handler.headers.get("Range", "")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match:
            handler._send_problem(416, "不支持的 Range 请求"); return
        first, last = match.groups()
        if not first and not last:
            handler._send_problem(416, "无效的 Range 请求"); return
        if first:
            start = int(first)
            end = int(last) if last else end
        else:
            suffix_size = int(last)
            start = max(0, total_size - suffix_size)
        if start >= total_size or end < start:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{total_size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        end = min(end, total_size - 1)
        status_code = 206
    content_length = max(0, end - start + 1)
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    ascii_suffix = file_path.suffix.lower() if file_path.suffix.lower() in ALLOWED_RESUME_SUFFIXES else ""
    encoded_name = quote(file_path.name, safe="")
    handler.send_response(status_code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(content_length))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Disposition", f"inline; filename=resume{ascii_suffix}; filename*=UTF-8''{encoded_name}")
    handler.send_header("Cache-Control", "private, no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    if status_code == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
    handler.end_headers()
    if not send_body:
        return
    with file_path.open("rb") as stream:
        stream.seek(start)
        remaining = content_length
        while remaining > 0:
            chunk = stream.read(min(64 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_problem(self, status: int, message: str):
        """发送 UTF-8 错误页，避免中文进入只支持 Latin-1 的 HTTP 状态行。"""
        body = (f'<!doctype html><meta charset="utf-8"><title>请求失败</title>'
                f'<body style="font-family:Microsoft YaHei,sans-serif;padding:32px">'
                f'<h2>请求失败（{status}）</h2><p>{escape(message)}</p>'
                f'<p><a href="/">返回总览</a></p></body>').encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _is_safe_local_request(self) -> bool:
        """拒绝 DNS rebinding Host，并限制浏览器跨源 POST。"""
        expected = {f"127.0.0.1:{_server_port}", f"localhost:{_server_port}"}
        if self.headers.get("Host", "") not in expected:
            return False
        origin = self.headers.get("Origin", "")
        return not origin or origin in {f"http://{item}" for item in expected}

    def do_HEAD(self):
        if not self._is_safe_local_request():
            self._send_problem(403, "请求来源不受信任"); return
        path = urlparse(self.path).path
        if path.startswith("/resume/"):
            try: _resume_response(self, int(path.rsplit("/", 1)[1]), send_body=False)
            except ValueError: self._send_problem(404, "简历记录不存在")
            return
        self._send_problem(404, "页面不存在")

    def do_GET(self):
        if not self._is_safe_local_request():
            self._send_problem(403, "请求来源不受信任"); return
        path = urlparse(self.path).path
        if path == "/favicon.ico":
            self.send_response(204); self.send_header("Content-Length", "0"); self.end_headers(); return
        if path == "/health":
            body = ('{"status":"ok","host":"127.0.0.1","port":%d}' % _server_port).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path.startswith("/resume/"):
            try: _resume_response(self, int(path.rsplit("/", 1)[1]))
            except ValueError: self._send_problem(404, "简历记录不存在")
            return
        if path == "/":
            body = _overview_page(_server_port)
        elif path == "/board":
            body = _board_page(_server_port)
        elif path == "/applications":
            body = _applications_page(_server_port)
        elif path == "/interviews":
            body = _interviews_page(_server_port)
        elif path == "/resumes":
            body = _resumes_page(_server_port)
        else:
            self._send_problem(404, "页面不存在"); return
        encoded = body.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)

    def do_POST(self):
        if not self._is_safe_local_request():
            self._send_problem(403, "请求来源不受信任"); return
        try:
            data, files = _parse_post(self)
            path = urlparse(self.path).path
            if path == "/application":
                company, position = data.get("company_name", "").strip(), data.get("position_name", "").strip()
                if not company or not position: raise ValueError("公司名称和岗位名称不能为空")
                status = data.get("status", "已投递")
                status = status if status in db_manager.APPLICATION_STATUSES else "已投递"
                priority = max(0, min(5, int(data.get("priority", 0) or 0)))
                resume_id = db_manager.add_resume(
                    company, position, _save_resume_upload(files.get("resume_file"), company, position),
                    jd_text=data.get("jd_text", "").strip(),
                    application_source=data.get("application_source", "").strip(),
                    job_link=data.get("job_link", "").strip(),
                )
                app_id = db_manager.add_application(resume_id, status, priority)
                db_manager.update_resume_details(resume_id, city=data.get("city", "").strip())
                db_manager.update_application_details(app_id, next_action=data.get("next_action", "").strip())
            elif path.endswith("/delete") and path.startswith("/application/"):
                _recycle_application(int(path.split("/")[2]))
            elif path.endswith("/reopen") and path.startswith("/application/"):
                app_id = int(path.split("/")[2])
                if not _find_application(app_id):
                    raise ValueError("投递记录不存在")
                db_manager.update_application_status(app_id, "已投递")
            elif path.startswith("/application/"):
                app_id = int(path.rsplit("/", 1)[1])
                status, previous = data.get("status", ""), data.get("previous_status", "")
                if status != previous and status in db_manager.APPLICATION_STATUSES: db_manager.update_application_status(app_id, status)
                db_manager.update_application_details(app_id, next_action=data.get("next_action", ""), priority=max(0, min(5, int(data.get("priority", 0) or 0))))
                app = _find_application(app_id)
                if app:
                    update_fields = {
                        "application_source": data.get("application_source", "").strip(),
                        "job_link": data.get("job_link", "").strip(),
                        "jd_text": data.get("jd_text", "").strip(),
                    }
                    if files.get("resume_file"):
                        update_fields["file_path"] = _save_resume_upload(files["resume_file"], app["company_name"], app["position_name"])
                    db_manager.update_resume_details(app["resume_id"], **update_fields)
            elif path == "/interview":
                db_manager.add_interview(int(data["application_id"]), data.get("round", "其他"), data.get("interview_time", ""), data.get("summary", ""))
            else:
                self._send_problem(404, "操作不存在"); return
        except (KeyError, ValueError) as exc:
            self._send_problem(400, str(exc)); return
        self.send_response(303)
        self.send_header("Location", "/applications" if path.startswith("/application") else "/interviews")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_):
        pass


def start_gateway(port=None) -> str:
    global _server, _server_port
    if _server is None:
        _server_port = int(port or get_port())
        _server = ThreadingHTTPServer((HOST, _server_port), _Handler)
        Thread(target=_server.serve_forever, name="ResumeDetectiveGateway", daemon=True).start()
    return get_url(_server_port)


def restart_gateway(port: int) -> str:
    old_port = _server_port
    if old_port == port: return get_url(port)
    stop_gateway()
    try: return start_gateway(port)
    except OSError:
        if old_port is not None: start_gateway(old_port)
        raise


def stop_gateway():
    global _server, _server_port
    if _server is not None:
        _server.shutdown(); _server.server_close(); _server = None; _server_port = None
