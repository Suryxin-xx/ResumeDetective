package store

const SchemaVersion = 7

const schemaV6 = `
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    position_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    city TEXT DEFAULT '',
    application_source TEXT DEFAULT '',
    job_link TEXT DEFAULT '',
    job_category TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    jd_text TEXT,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version_note TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER NOT NULL,
    current_status TEXT NOT NULL,
    stage_state TEXT NOT NULL DEFAULT '已完成，等待结果',
    priority INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    status_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    interview_feedback TEXT,
    next_action TEXT,
    applied_at TEXT DEFAULT '',
    application_deadline TEXT DEFAULT '',
    next_action_due_at TEXT DEFAULT '',
    last_follow_up_at TEXT DEFAULT '',
    status_history TEXT DEFAULT '',
    FOREIGN KEY (resume_id) REFERENCES resumes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_type TEXT, title TEXT, content TEXT NOT NULL, tags TEXT,
    start_time TEXT DEFAULT '', end_time TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT DEFAULT '', gender TEXT DEFAULT '', birth_date TEXT DEFAULT '', phone TEXT DEFAULT '',
    email TEXT DEFAULT '', city TEXT DEFAULT '', education TEXT DEFAULT '', school TEXT DEFAULT '',
    major TEXT DEFAULT '', target_role TEXT DEFAULT '', summary TEXT DEFAULT '', github_url TEXT DEFAULT '',
    portfolio_url TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS job_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL, position_name TEXT NOT NULL, jd_text TEXT DEFAULT '', jd_link TEXT DEFAULT '',
    city TEXT DEFAULT '', status TEXT DEFAULT '待研究' CHECK (status IN ('待研究','待投递','已投递','暂不考虑')),
    notes TEXT DEFAULT '', priority INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS application_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL, display_name TEXT DEFAULT '',
    file_name TEXT NOT NULL, file_path TEXT NOT NULL, file_type TEXT DEFAULT '', source_type TEXT DEFAULT '',
    notes TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS job_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, due_date TEXT DEFAULT '', priority INTEGER DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'done')), scope_type TEXT DEFAULT '', scope_id INTEGER,
    notes TEXT DEFAULT '', source TEXT DEFAULT 'manual', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL, round TEXT NOT NULL DEFAULT '一面',
    interview_time TEXT DEFAULT '', summary TEXT DEFAULT '', result TEXT DEFAULT '待确认', questions TEXT DEFAULT '',
    weak_points TEXT DEFAULT '', follow_up TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS demo_records (
    entity_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    PRIMARY KEY (entity_type, record_id)
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(current_status);
CREATE INDEX IF NOT EXISTS idx_applications_updated ON applications(status_update_time DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_state_due ON job_tasks(state, due_date);
CREATE INDEX IF NOT EXISTS idx_interviews_application ON interviews(application_id);
PRAGMA user_version = 7;
`
