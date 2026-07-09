"""
数据库管理模块
负责 SQLite 数据库的初始化和 CRUD 操作
"""

import sqlite3
from pathlib import Path

import file_ops
from paths import DB_FILE, DATA_DIR

# DDL 建表语句
DDL_STATEMENTS = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    position_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    city TEXT DEFAULT '',
    jd_text TEXT,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version_note TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER NOT NULL,
    current_status TEXT NOT NULL
        CHECK (current_status IN ('已投递','简历初筛','笔试/无笔试','业务面试','HR面','Offer','终止')),
    priority INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    status_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    interview_feedback TEXT,
    next_action TEXT,
    status_history TEXT DEFAULT '',
    FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_type TEXT,
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT,
    start_time TEXT DEFAULT '',
    end_time TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT DEFAULT '',
    gender TEXT DEFAULT '',
    birth_date TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    city TEXT DEFAULT '',
    education TEXT DEFAULT '',
    school TEXT DEFAULT '',
    major TEXT DEFAULT '',
    target_role TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    github_url TEXT DEFAULT '',
    portfolio_url TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    position_name TEXT NOT NULL,
    jd_text TEXT DEFAULT '',
    jd_link TEXT DEFAULT '',
    city TEXT DEFAULT '',
    status TEXT DEFAULT '待研究'
        CHECK (status IN ('待研究','待投递','已投递','暂不考虑')),
    notes TEXT DEFAULT '',
    priority INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    display_name TEXT DEFAULT '',
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（每次创建新连接，确保线程安全）"""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库：建表（幂等操作）"""
    conn = get_connection()
    try:
        conn.executescript(DDL_STATEMENTS)
        # 迁移：添加 status_history 列
        try:
            conn.execute("ALTER TABLE applications ADD COLUMN status_history TEXT DEFAULT ''")
        except Exception:
            pass
        # 迁移：materials 时间字段
        try:
            conn.execute("ALTER TABLE materials ADD COLUMN start_time TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE materials ADD COLUMN end_time TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE materials ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass
        # 迁移：priority / sort_order
        for col in ["priority INTEGER DEFAULT 0", "sort_order INTEGER DEFAULT 0"]:
            try:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()
        # 迁移 v2: resumes.file_path NOT NULL → DEFAULT ''
        try:
            info = conn.execute("PRAGMA table_info(resumes)").fetchall()
            fp_col = next((r for r in info if r["name"] == "file_path"), None)
            if fp_col and fp_col["notnull"] == 1:
                conn.executescript("""
                    PRAGMA foreign_keys = OFF;
                    CREATE TABLE resumes_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_name TEXT NOT NULL,
                        position_name TEXT NOT NULL,
                        file_path TEXT DEFAULT '',
                        jd_text TEXT,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        version_note TEXT
                    );
                    INSERT INTO resumes_v2 SELECT * FROM resumes;
                    DROP TABLE resumes;
                    ALTER TABLE resumes_v2 RENAME TO resumes;
                    PRAGMA foreign_keys = ON;
                """)
        except Exception:
            pass
        conn.commit()
        # 迁移 v3: resumes.city + job_targets priority/sort_order
        for tbl, col in [
            ("resumes", "city TEXT DEFAULT ''"),
            ("job_targets", "priority INTEGER DEFAULT 0"),
            ("job_targets", "sort_order INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


# ─── Resume CRUD ───────────────────────────────────────────

def add_resume(company_name, position_name, file_path, jd_text="", version_note=""):
    """新增简历，返回新纪录的 id"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO resumes (company_name, position_name, file_path, jd_text, version_note) "
            "VALUES (?, ?, ?, ?, ?)",
            (company_name, position_name, file_path, jd_text, version_note),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_all_resumes():
    """获取所有简历列表"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM resumes ORDER BY upload_time DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_resume(resume_id):
    """删除指定简历（级联删除对应 application + 简历文件移入回收站）"""
    conn = get_connection()
    try:
        # 先获取文件路径
        row = conn.execute("SELECT file_path FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        file_path = row["file_path"] if row else ""

        conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
        conn.commit()
    finally:
        conn.close()

    # 简历文件移入回收站；失败时保留原文件，避免误删资料
    if file_path:
        fp = Path(file_path)
        if not fp.is_absolute():
            fp = Path(__file__).parent / file_path
        ok, msg = file_ops.recycle_path(fp)
        if not ok:
            print(f"[文件] {msg}: {fp}")


# ─── Application CRUD ──────────────────────────────────────

def add_application(resume_id, status="已投递", priority=0):
    """新增投递记录，返回新纪录的 id"""
    conn = get_connection()
    try:
        max_sort = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM applications").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO applications (resume_id, current_status, priority, sort_order) VALUES (?, ?, ?, ?)",
            (resume_id, status, priority, max_sort + 1),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_application_status(app_id, new_status):
    """更新投递状态，刷新时间戳，记录历史"""
    conn = get_connection()
    try:
        # 获取当前状态历史
        row = conn.execute(
            "SELECT current_status, status_history FROM applications WHERE id = ?",
            (app_id,),
        ).fetchone()
        if row is None:
            return
        old_status = row["current_status"]
        history = row["status_history"] or ""

        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"{ts}: {old_status} → {new_status}"
        if history:
            history = history + "\n" + entry
        else:
            history = entry

        conn.execute(
            "UPDATE applications SET current_status = ?, status_update_time = CURRENT_TIMESTAMP, "
            "status_history = ? WHERE id = ?",
            (new_status, history, app_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_priority(app_id, priority):
    """更新优先级"""
    conn = get_connection()
    try:
        conn.execute("UPDATE applications SET priority = ? WHERE id = ?", (priority, app_id))
        conn.commit()
    finally:
        conn.close()


def update_sort_order(app_id, sort_order):
    """更新排序序号"""
    conn = get_connection()
    try:
        conn.execute("UPDATE applications SET sort_order = ? WHERE id = ?", (sort_order, app_id))
        conn.commit()
    finally:
        conn.close()


def get_applications_with_resume():
    """联表查询所有投递记录（含简历信息和状态历史）"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT a.id, a.resume_id, a.current_status, a.status_update_time, "
            "       a.interview_feedback, a.next_action, a.status_history, "
            "       a.priority, a.sort_order, "
            "       r.company_name, r.position_name, r.file_path, r.city, r.jd_text, r.upload_time "
            "FROM applications a "
            "JOIN resumes r ON a.resume_id = r.id "
            "ORDER BY a.sort_order ASC, a.status_update_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Material CRUD ─────────────────────────────────────────

def add_material(material_type, title, content, tags="", start_time="", end_time=""):
    """新增个人经历碎片"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO materials (material_type, title, content, tags, start_time, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (material_type, title, content, tags, start_time, end_time),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def search_materials(keyword):
    """用 LIKE 模糊搜索 content 和 tags，取前 3 条"""
    conn = get_connection()
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            "SELECT * FROM materials WHERE content LIKE ? OR tags LIKE ? LIMIT 3",
            (pattern, pattern),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_materials():
    """获取所有经历碎片（按创建时间倒序）"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM materials ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_materials_filtered(material_type="", keyword="", start_date="", end_date=""):
    """
    按条件筛选经历碎片
    material_type: 类型精确匹配（空=全部）
    keyword: 搜索 title/content/tags（LIKE）
    start_date/end_date: 起止时间范围（按 created_at）
    """
    conn = get_connection()
    try:
        sql = "SELECT * FROM materials WHERE 1=1"
        params = []
        if material_type:
            sql += " AND material_type = ?"
            params.append(material_type)
        if keyword:
            sql += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        if start_date:
            sql += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND created_at <= ?"
            params.append(end_date + " 23:59:59")
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_material(mid, material_type, title, content, tags, start_time="", end_time=""):
    """更新经历碎片"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE materials SET material_type=?, title=?, content=?, tags=?, start_time=?, end_time=? "
            "WHERE id=?",
            (material_type, title, content, tags, start_time, end_time, mid),
        )
        conn.commit()
    finally:
        conn.close()


def delete_material(material_id):
    """删除指定经历碎片"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
    finally:
        conn.close()


# ─── Profile CRUD ─────────────────────────────────────────

def get_profile():
    """获取个人信息（profile 表只有一条记录）"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM profile LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_profile(data: dict):
    """保存/更新个人信息。存在则更新，不存在则插入。"""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM profile LIMIT 1").fetchone()
        if existing:
            sql = (
                "UPDATE profile SET full_name=?, gender=?, birth_date=?, phone=?, email=?, "
                "city=?, education=?, school=?, major=?, target_role=?, summary=?, "
                "github_url=?, portfolio_url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?"
            )
            conn.execute(sql, (
                data.get("full_name", ""), data.get("gender", ""),
                data.get("birth_date", ""), data.get("phone", ""),
                data.get("email", ""), data.get("city", ""),
                data.get("education", ""), data.get("school", ""),
                data.get("major", ""), data.get("target_role", ""),
                data.get("summary", ""), data.get("github_url", ""),
                data.get("portfolio_url", ""), existing["id"],
            ))
        else:
            sql = (
                "INSERT INTO profile (full_name, gender, birth_date, phone, email, city, "
                "education, school, major, target_role, summary, github_url, portfolio_url) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            )
            conn.execute(sql, (
                data.get("full_name", ""), data.get("gender", ""),
                data.get("birth_date", ""), data.get("phone", ""),
                data.get("email", ""), data.get("city", ""),
                data.get("education", ""), data.get("school", ""),
                data.get("major", ""), data.get("target_role", ""),
                data.get("summary", ""), data.get("github_url", ""),
                data.get("portfolio_url", ""),
            ))
        conn.commit()
    finally:
        conn.close()


# ─── JobTarget CRUD ───────────────────────────────────────

def add_job_target(company_name, position_name, jd_text="", jd_link="",
                   city="", status="待研究", notes="", priority=0):
    """新增意向公司/岗位，返回新记录 id"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO job_targets (company_name, position_name, jd_text, jd_link, city, status, notes, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (company_name, position_name, jd_text, jd_link, city, status, notes, priority),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_all_job_targets():
    """获取所有意向公司（按创建时间倒序）"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM job_targets ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job_targets_filtered(status="", keyword=""):
    """按状态和关键字筛选意向公司"""
    conn = get_connection()
    try:
        sql = "SELECT * FROM job_targets WHERE 1=1"
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if keyword:
            sql += " AND (company_name LIKE ? OR position_name LIKE ? OR jd_text LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        sql += " ORDER BY updated_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_job_target_priority(jt_id, priority):
    """更新意向公司优先级"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE job_targets SET priority=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (priority, jt_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_job_target(jt_id, company_name, position_name, jd_text="", jd_link="",
                      city="", status="", notes="", priority=None):
    """更新意向公司信息"""
    conn = get_connection()
    try:
        sql = "UPDATE job_targets SET company_name=?, position_name=?, jd_text=?, jd_link=?, "
        params = [company_name, position_name, jd_text, jd_link]
        if priority is not None:
            sql += "priority=?, "
            params.append(priority)
        sql += "city=?, status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?"
        params.extend([city, status, notes, jt_id])
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def delete_job_target(jt_id):
    """删除指定意向公司"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM job_targets WHERE id = ?", (jt_id,))
        conn.commit()
    finally:
        conn.close()


def convert_job_target_to_application(jt_id):
    """
    将意向公司转为投递记录（保留公司名、岗位名、JD）
    因为转为投递时可能没有简历文件，file_path 留空。
    返回 (success: bool, message/application_id)
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM job_targets WHERE id = ?", (jt_id,)
        ).fetchone()
        if row is None:
            return False, "未找到该意向公司记录（id=%s）" % jt_id
        jt = dict(row)
        # 创建 resume 记录，file_path 留空，带上 city
        cur = conn.execute(
            "INSERT INTO resumes (company_name, position_name, file_path, city, jd_text) VALUES (?, ?, '', ?, ?)",
            (jt["company_name"], jt["position_name"], jt.get("city", ""), jt.get("jd_text", "")),
        )
        rid = cur.lastrowid
        cur2 = conn.execute(
            "INSERT INTO applications (resume_id, current_status) VALUES (?, '已投递')",
            (rid,),
        )
        app_id = cur2.lastrowid
        conn.execute(
            "UPDATE job_targets SET status='已投递', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (jt_id,),
        )
        conn.commit()
        return True, app_id
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, "转换失败：%s" % str(e)
    finally:
        conn.close()


# ─── Attachment CRUD ──────────────────────────────────

def add_attachment(application_id, file_name, file_path, display_name="",
                   file_type="", source_type="", notes=""):
    """新增附件，返回新记录 id"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO application_attachments "
            "(application_id, display_name, file_name, file_path, file_type, source_type, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (application_id, display_name, file_name, file_path, file_type, source_type, notes),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_attachments(application_id):
    """获取指定投递记录的所有附件"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM application_attachments WHERE application_id = ? ORDER BY created_at",
            (application_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_attachment_notes(att_id, notes):
    """更新附件备注"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE application_attachments SET notes = ? WHERE id = ?",
            (notes, att_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_attachment(att_id):
    """删除附件记录，返回文件路径以便移入回收站"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT file_path FROM application_attachments WHERE id = ?", (att_id,)).fetchone()
        file_path = row["file_path"] if row else ""
        conn.execute("DELETE FROM application_attachments WHERE id = ?", (att_id,))
        conn.commit()
        return file_path
    finally:
        conn.close()


def get_attachment_count(application_id):
    """获取指定投递的附件数量"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM application_attachments WHERE application_id = ?",
            (application_id,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def delete_attachments_by_application(application_id):
    """删除某个投递的所有附件，返回文件路径列表"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT file_path FROM application_attachments WHERE application_id = ?",
            (application_id,),
        ).fetchall()
        paths = [r["file_path"] for r in rows]
        conn.execute("DELETE FROM application_attachments WHERE application_id = ?", (application_id,))
        conn.commit()
        return paths
    finally:
        conn.close()
