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
    return str(target.relative_to(paths.ROOT_DIR)).replace("\\", "/")


def _absolute_data_path(relative_path: str) -> Path:
    candidate = Path(relative_path)
    return candidate if candidate.is_absolute() else paths.ROOT_DIR / candidate


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
button,.btn,input,select,textarea{min-height:40px;transition:border-color .16s,box-shadow .16s,background .16s,transform .08s}button,.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none;padding:9px 14px}button:active,.btn:active{transform:translateY(1px)}input:focus,select:focus,textarea:focus{outline:none;border-color:#6e97eb;box-shadow:0 0 0 3px rgba(45,104,223,.12)}select{appearance:none;-webkit-appearance:none;padding-right:34px;background-color:#fff;background-image:linear-gradient(45deg,transparent 50%,#68778e 50%),linear-gradient(135deg,#68778e 50%,transparent 50%);background-position:calc(100% - 16px) 17px,calc(100% - 11px) 17px;background-size:5px 5px,5px 5px;background-repeat:no-repeat}input[type=file]{padding:6px 8px;background:#f8faff;border:1px solid #d8e0eb;border-radius:8px;color:#66758a}input[type=file]::file-selector-button{height:28px;border:0;border-radius:6px;background:#e9f0ff;color:#245dc9;font-weight:700;padding:0 11px;margin-right:10px;cursor:pointer}input[type=file]::file-selector-button:hover{background:#dce8ff}.ghost,.filter-chip{background:#edf2fe;color:#275fce;border:1px solid transparent}.filter-chips{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0 16px}.filter-chip{min-height:34px;padding:6px 10px;border-radius:99px;font-size:12px}.filter-chip.active{background:#2d68df;color:#fff}.board-toolbar{display:flex;gap:8px;align-items:center}.board-toolbar input{width:280px}.board-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:13px;align-items:start}.lane{background:#f7f9fc;border:1px solid #dfe5ee;border-radius:13px;padding:12px;min-width:0}.lane-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.lane-head h3{display:flex;align-items:center;gap:7px}.lane-count{display:inline-flex;align-items:center;justify-content:center;min-width:25px;height:25px;border-radius:99px;background:#e7ecf4;color:#536279;font-size:12px}.lane-card{background:#fff;border:1px solid #e3e8f0;border-radius:10px;padding:12px;margin-top:8px;box-shadow:0 3px 10px rgba(25,37,62,.04)}.lane-card:first-of-type{margin-top:0}.lane-card b{display:block}.lane-card p{margin:5px 0 0;color:#59677b;font-size:13px}.lane-card small{display:block;margin-top:8px;color:#7a8799}.lane-empty{color:#8894a5;font-size:12px;padding:12px 3px}.review-form{display:grid;grid-template-columns:1.2fr .8fr 1fr;gap:12px;align-items:end}.review-form .wide{grid-column:1/-1}.review-form button{width:max-content;min-width:135px}.field-file{padding:10px;border:1px dashed #cad5e4;border-radius:10px;background:#fbfcff}.field-file input{width:100%;margin-top:2px}.results-summary{color:#6f7c91;font-size:12px;margin-left:auto}
@media(max-width:700px){.board-toolbar{align-items:stretch;flex-direction:column}.board-toolbar input{width:100%}.review-form{grid-template-columns:1fr}.review-form .wide{grid-column:auto}.review-form button{width:100%}.filter-chips{gap:5px}.filter-chip{flex:1 0 auto}}
</style>'''

ARCHIVE_STYLES = '''<style>
.archive{grid-column:1/-1;border:1px solid #e1e7f0;border-radius:10px;background:#fafbfe;overflow:hidden}.archive summary{cursor:pointer;padding:10px 12px;color:#3e5069;font-weight:700}.archive-fields{display:grid;grid-template-columns:1fr 1.4fr;gap:10px;padding:0 12px 12px}.archive-fields .full{grid-column:1/-1}.archive-fields textarea{min-height:130px}.add-form .full{grid-column:1/-1}.source-note{color:#768397;font-size:11px;margin-top:5px}.job-link{color:#2864d2;text-decoration:none;word-break:break-all}.job-link:hover{text-decoration:underline}
@media(max-width:700px){.archive-fields{grid-template-columns:1fr}.archive-fields .full,.add-form .full{grid-column:auto}}
</style>'''


def _layout(title: str, current: str, body: str, port: int) -> str:
    nav = f'''<nav><a class="{"active" if current == "overview" else ""}" href="/">总览</a><a class="{"active" if current == "board" else ""}" href="/board">状态看板</a><a class="{"active" if current == "applications" else ""}" href="/applications">投递管理</a></nav>'''
    body = UI_ENHANCEMENTS + ARCHIVE_STYLES + body
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · Resume Detective</title><style>
    :root{{--bg:#f5f7fb;--paper:#fff;--ink:#182235;--muted:#6f7c91;--line:#e4e9f1;--brand:#2d68df;--danger:#cb3a46;--shadow:0 8px 26px rgba(25,37,62,.07)}}*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px "Microsoft YaHei","PingFang SC",sans-serif}}.shell{{width:100%;max-width:1220px;margin:auto;padding:0 20px 50px}}header{{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:24px 0 17px;border-bottom:1px solid var(--line)}}h1{{margin:0;font-size:22px}}.local{{font-size:12px;font-weight:700;color:#187546;background:#e7f8ee;padding:7px 10px;border-radius:99px;white-space:nowrap}}nav{{display:flex;flex-wrap:wrap;gap:6px;padding:15px 0}}nav a{{text-decoration:none;color:#56657c;padding:8px 12px;border-radius:8px;font-weight:700}}nav a:hover{{background:#eaf0ff;color:#235bcd}}nav a.active{{background:#2d68df;color:#fff}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:2px 0 16px}}.stat,.panel{{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}}.stat{{padding:15px 17px}}.stat span,.hint{{color:var(--muted);font-size:12px}}.stat b{{display:block;font-size:25px;margin-top:5px}}.stat.primary{{background:linear-gradient(130deg,#2b66dd,#6793ec);border:0;color:#fff}}.stat.primary span{{color:#dfeaff}}.panel{{padding:20px;margin-bottom:16px}}.panel-head{{display:flex;justify-content:space-between;gap:15px;align-items:start;margin-bottom:16px}}h2{{margin:0 0 5px;font-size:17px}}h3{{margin:0;font-size:16px}}.grid-two{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}form{{margin:0}}label{{display:grid;gap:6px;color:#526177;font-size:12px;font-weight:700}}input,select,textarea,button{{font:inherit;border-radius:8px;padding:9px 10px}}input,select,textarea{{border:1px solid #d8e0eb;background:#fff;color:var(--ink);min-width:0}}textarea{{min-height:92px;resize:vertical;line-height:1.5}}button{{border:0;background:var(--brand);color:#fff;font-weight:700;cursor:pointer}}button:hover{{background:#1e57ca}}button.danger{{background:#fff0f1;color:var(--danger)}}button.danger:hover{{background:#ffe3e5}}.add-form{{display:grid;grid-template-columns:1fr 1.15fr .75fr .8fr .55fr;gap:12px;align-items:end}}.add-form .wide{{grid-column:span 2}}.add-form .file{{grid-column:span 2}}.add-form button{{height:39px}}.toolbar{{display:flex;gap:8px;align-items:center}}.toolbar input{{width:260px}}.ghost{{background:#edf2fe;color:#275fce}}.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.card{{border:1px solid var(--line);border-radius:12px;padding:16px;background:#fff}}.card-top{{display:flex;justify-content:space-between;gap:10px;align-items:start;margin-bottom:13px}}.card-top p{{margin:5px 0 0;color:#526078}}.card-top p span{{color:var(--muted)}}.badge{{padding:5px 8px;border-radius:7px;font-size:12px;font-weight:700;white-space:nowrap}}.blue{{background:#e9f1ff;color:#245fd4}}.amber{{background:#fff1dc;color:#b86508}}.purple{{background:#f1eaff;color:#7441b5}}.green{{background:#e3f7ec;color:#197c4b}}.cyan{{background:#dff5f8;color:#1a7687}}.rose{{background:#ffe7ee;color:#ae3157}}.gray{{background:#eef1f5;color:#66758a}}.manage-form{{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:end}}.manage-form .wide{{grid-column:1/-1}}.resume-row{{display:flex;gap:8px;align-items:center;padding:10px;border:1px dashed #cbd5e3;border-radius:9px;grid-column:1/-1}}.resume-row input{{padding:0;border:0;flex:1;max-width:100%}}.resume-row a{{font-size:12px;color:#2460d0;white-space:nowrap}}.actions{{display:flex;gap:8px;grid-column:1/-1}}.actions button{{flex:1}}.delete-form{{display:contents}}.todo,.reviews{{list-style:none;padding:0;margin:0}}.todo li,.review{{padding:11px 0;border-top:1px solid var(--line);line-height:1.5}}.todo li:first-child,.review:first-child{{border-top:0;padding-top:0}}time{{font-size:12px;color:#52647c;display:inline-block;min-width:90px}}time.overdue{{color:#be3740}}.review small{{display:block;color:var(--muted);margin-top:5px}}.review p{{margin:7px 0 0;white-space:pre-wrap;color:#4d5a6e}}.next-list{{display:grid;gap:10px}}.next-item{{border:1px solid var(--line);border-radius:10px;padding:12px}}.next-item b{{display:block}}.next-item p{{margin:5px 0 0;color:#48566c}}.empty{{margin:0;color:var(--muted);line-height:1.6}}.hidden{{display:none}}@media(max-width:850px){{.add-form{{grid-template-columns:1fr 1fr}}.add-form .wide,.add-form .file{{grid-column:auto}}.add-form button{{grid-column:1/-1}}.cards,.grid-two{{grid-template-columns:1fr}}}}@media(max-width:580px){{.shell{{padding:0 13px 36px}}header{{align-items:flex-start;flex-direction:column}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}.panel{{padding:16px}}.panel-head{{flex-direction:column}}.toolbar input{{width:100%}}.add-form,.manage-form{{grid-template-columns:1fr}}.add-form .wide,.add-form .file,.manage-form .wide{{grid-column:auto}}.resume-row{{grid-column:auto;align-items:start;flex-direction:column}}.actions{{grid-column:auto;flex-direction:column}}}}</style></head><body><main class="shell"><header><h1>秋招工作台</h1><div class="local">仅本机访问 · 127.0.0.1:{port}</div></header>{nav}{body}</main></body></html>'''


def _overview_page(port: int) -> str:
    apps, tasks, interviews = db_manager.get_applications_with_resume(), db_manager.get_job_tasks("open"), db_manager.get_interviews()
    active = [item for item in apps if item["current_status"] not in ("Offer", "终止")]
    today, week = date.today().isoformat(), (date.today() + timedelta(days=7)).isoformat()
    upcoming = [item for item in tasks if item.get("due_date") and item["due_date"] <= week][:8]
    next_actions = [item for item in active if item.get("next_action")][:8]
    todo_html = "".join(f'<li><time class="{"overdue" if item["due_date"] < today else ""}">{escape(item["due_date"])}</time>{escape(item["title"])}</li>' for item in upcoming) or '<li class="empty">未来 7 天没有已安排待办。</li>'
    next_html = "".join(f'<article class="next-item"><b>{escape(item["company_name"])} · {escape(item["position_name"])}</b><p>{escape(item["next_action"])}</p></article>' for item in next_actions) or '<p class="empty">流程中岗位暂未填写下一步行动。</p>'
    review_html = "".join(f'<article class="review"><b>{escape(item["company_name"])} · {escape(item["position_name"])} · {escape(item["round"])}</b><small>{escape(item["interview_time"] or "未填时间")}</small><p>{escape(item["summary"] or "未填写复盘内容")}</p></article>' for item in interviews[:5]) or '<p class="empty">暂无面试复盘。</p>'
    app_options = "".join(f'<option value="{item["id"]}">{escape(item["company_name"])} · {escape(item["position_name"])}</option>' for item in apps)
    review_form = f'''<form class="review-form" method="post" action="/interview"><label>对应岗位<select name="application_id" required>{app_options}</select></label><label>面试轮次<select name="round"><option>一面</option><option>二面</option><option>三面</option><option>HR 面</option><option>其他</option></select></label><label>面试时间<input name="interview_time" type="datetime-local"></label><label class="wide">复盘内容<textarea name="summary" placeholder="问题、没答好的内容、复盘结论和后续补强点"></textarea></label><button {"disabled" if not apps else ""}>保存面试复盘</button></form>'''
    body = f'''<section class="stats"><div class="stat primary"><span>全部投递</span><b>{len(apps)}</b></div><div class="stat"><span>流程中</span><b>{len(active)}</b></div><div class="stat"><span>面试阶段</span><b>{sum(item["current_status"] in ("业务面试", "HR面") for item in apps)}</b></div><div class="stat"><span>Offer</span><b>{sum(item["current_status"] == "Offer" for item in apps)}</b></div></section>
    <div class="grid-two"><section class="panel"><div class="panel-head"><div><h2>近期待办</h2><div class="hint">未来 7 天内的行动清单</div></div></div><ul class="todo">{todo_html}</ul></section><section class="panel"><div class="panel-head"><div><h2>流程中的下一步</h2><div class="hint">来自岗位投递记录</div></div></div><div class="next-list">{next_html}</div></section></div><section class="panel"><div class="panel-head"><div><h2>新增面试复盘</h2><div class="hint">一条记录对应一轮面试</div></div></div>{review_form}</section><section class="panel"><div class="panel-head"><div><h2>最近面试复盘</h2><div class="hint">每轮面试单独记录</div></div></div><div class="reviews">{review_html}</div></section>'''
    return _layout("总览", "overview", body, port)


def _board_page(port: int) -> str:
    """按状态分组的自适应看板；不使用横向无限滚动。"""
    apps = db_manager.get_applications_with_resume()
    lanes = []
    for status in db_manager.APPLICATION_STATUSES:
        status_apps = [item for item in apps if item["current_status"] == status]
        cards = "".join(
            f'''<article class="lane-card" data-search="{escape((str(item.get("company_name") or "") + " " + str(item.get("position_name") or "") + " " + str(item.get("city") or "") + " " + str(item.get("application_source") or "") + " " + str(item.get("next_action") or "")).lower())}"><b>{escape(item["company_name"])}</b><p>{escape(item["position_name"])} · {escape(item.get("city") or "地点未填")}</p><small>来源：{escape(item.get("application_source") or "未记录")}<br>下一步：{escape(item.get("next_action") or "暂未填写")}</small></article>'''
            for item in status_apps
        ) or '<div class="lane-empty">暂无岗位</div>'
        lanes.append(f'''<section class="lane"><div class="lane-head"><h3><span class="badge {_status_class(status)}">{escape(status)}</span></h3><span class="lane-count">{len(status_apps)}</span></div>{cards}</section>''')
    body = f'''<section class="panel"><div class="panel-head"><div><h2>投递状态看板</h2><div class="hint">按当前流程自动分组；状态更新请前往“投递管理”。</div></div><div class="board-toolbar"><input id="boardSearch" placeholder="搜索公司、岗位、地点或下一步"><a class="btn ghost" href="/applications">管理投递</a></div></div><div class="board-grid" id="board">{''.join(lanes)}</div></section><script>const boardSearch=document.querySelector('#boardSearch');boardSearch.addEventListener('input',()=>{{const q=boardSearch.value.toLowerCase();document.querySelectorAll('.lane-card[data-search]').forEach(card=>card.classList.toggle('hidden',q&&!card.dataset.search.includes(q)));document.querySelectorAll('.lane').forEach(lane=>{{const visible=[...lane.querySelectorAll('.lane-card')].some(card=>!card.classList.contains('hidden'));lane.classList.toggle('hidden',q&&!visible)}})}});</script>'''
    return _layout("状态看板", "board", body, port)


def _applications_page(port: int) -> str:
    apps = db_manager.get_applications_with_resume()
    cards = []
    for app in apps:
        app_id, priority = app["id"], int(app.get("priority") or 0)
        resume_name = Path(app.get("file_path") or "").name or "尚未绑定简历"
        resume_link = f'<a href="/resume/{app_id}" target="_blank">查看简历</a>' if app.get("file_path") else ""
        job_link_view = f'<a class="job-link" href="{escape(app.get("job_link") or "")}" target="_blank" rel="noopener noreferrer">打开原岗位页面</a>' if app.get("job_link") else '<span class="hint">未记录岗位链接</span>'
        cards.append(f'''<article class="card" data-status="{escape(app["current_status"])}" data-search="{escape(' '.join(str(app.get(key) or '') for key in ('company_name','position_name','city','current_status','next_action'))).lower()}"><div class="card-top"><div><h3>{escape(app["company_name"])}</h3><p>{escape(app["position_name"])} <span>· {escape(app.get("city") or "地点未填")}</span></p></div><span class="badge {_status_class(app["current_status"])}">{escape(app["current_status"])}</span></div>
        <form class="manage-form" method="post" action="/application/{app_id}" enctype="multipart/form-data"><input type="hidden" name="previous_status" value="{escape(app["current_status"])}"><label>更新状态<select name="status">{_status_options(app["current_status"])}</select></label><label>优先级<select name="priority">{_priority_options(priority)}</select></label><label class="wide">下一步行动<input name="next_action" value="{escape(app.get("next_action") or "")}" placeholder="例如：准备一面"></label><details class="archive"><summary>投递来源与 JD 存档</summary><div class="archive-fields"><label>投递来源<input name="application_source" value="{escape(app.get("application_source") or "")}" placeholder="官网 / 内推 / 牛客 / 招聘群"></label><label>岗位原始链接<input name="job_link" type="url" value="{escape(app.get("job_link") or "")}" placeholder="https://..."></label><div class="full">{job_link_view}</div><label class="full">JD 原文快照<textarea name="jd_text" placeholder="粘贴完整 JD，岗位关闭后仍可复盘">{escape(app.get("jd_text") or "")}</textarea></label></div></details><div class="resume-row field-file"><div><b>关联简历</b><div class="hint">{escape(resume_name)}</div></div>{resume_link}<input type="file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"><span class="hint">选择文件后保存即可绑定/替换</span></div><div class="actions"><button>保存修改</button><button formmethod="post" formaction="/application/{app_id}/delete" class="danger" onclick="return confirm('确认删除这条投递吗？关联简历和附件会移入系统回收站。');">删除投递</button></div></form></article>''')
    cards_html = "".join(cards) or '<p class="empty">暂无投递记录。</p>'
    status_counts = {status: sum(app["current_status"] == status for app in apps) for status in db_manager.APPLICATION_STATUSES}
    filter_html = '<button type="button" class="filter-chip active" data-status="">全部 · %d</button>' % len(apps) + "".join(f'<button type="button" class="filter-chip" data-status="{escape(status)}">{escape(status)} · {status_counts[status]}</button>' for status in db_manager.APPLICATION_STATUSES)
    body = f'''<section class="panel"><div class="panel-head"><div><h2>新增投递</h2><div class="hint">保存来源、链接和 JD 快照，即使岗位关闭也能复盘。</div></div></div><form class="add-form" method="post" action="/application" enctype="multipart/form-data"><label>公司名称<input required name="company_name" placeholder="例如：字节跳动"></label><label>岗位名称<input required name="position_name" placeholder="例如：后端开发工程师"></label><label>工作地点<input name="city" placeholder="北京"></label><label>当前状态<select name="status">{_status_options()}</select></label><label>优先级<select name="priority">{_priority_options()}</select></label><label class="wide">下一步行动<input name="next_action" placeholder="例如：完成网申、准备笔试"></label><label>投递来源<input name="application_source" placeholder="官网 / 内推 / 牛客"></label><label class="wide">岗位原始链接<input name="job_link" type="url" placeholder="https://..."></label><label class="full">JD 原文快照<textarea name="jd_text" placeholder="粘贴完整岗位描述，便于后期复盘"></textarea></label><label class="file field-file">关联本地简历（可选）<input type="file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"></label><button>添加投递</button></form></section>
    <section class="panel"><div class="panel-head"><div><h2>投递管理</h2><div class="hint">按状态快速筛选，也可搜索公司、岗位、地点或下一步。</div></div><div class="toolbar"><input id="search" placeholder="搜索公司、岗位、地点或下一步"><span class="results-summary" id="resultsSummary"></span></div></div><div class="filter-chips" id="statusFilters">{filter_html}</div><div class="cards" id="cards">{cards_html}</div></section><script>const search=document.querySelector('#search'),summary=document.querySelector('#resultsSummary');let selectedStatus='';function applyFilters(){{const q=search.value.toLowerCase();let visible=0;document.querySelectorAll('.card[data-search]').forEach(card=>{{const show=(!q||card.dataset.search.includes(q))&&(!selectedStatus||card.dataset.status===selectedStatus);card.classList.toggle('hidden',!show);if(show)visible++}});summary.textContent='显示 '+visible+' 条'}}search.addEventListener('input',applyFilters);document.querySelectorAll('.filter-chip').forEach(button=>button.addEventListener('click',()=>{{document.querySelectorAll('.filter-chip').forEach(item=>item.classList.remove('active'));button.classList.add('active');selectedStatus=button.dataset.status;applyFilters()}}));applyFilters();</script>'''
    return _layout("投递管理", "applications", body, port)


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
        self.send_header("Location", "/applications" if path.startswith("/application") else "/")
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
