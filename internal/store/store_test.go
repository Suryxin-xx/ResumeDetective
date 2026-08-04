package store

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"testing"
)

func TestCreateApplicationUsesLocalTimeAndHistory(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	id, err := st.CreateApplication(context.Background(), CreateApplicationInput{CompanyName: "测试公司", PositionName: "Go 开发", Source: "官网", Category: "研发"})
	if err != nil {
		t.Fatal(err)
	}
	if id < 1 {
		t.Fatalf("invalid id %d", id)
	}
	items, err := st.ListApplications(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("got %d applications", len(items))
	}
	item := items[0]
	if item.CurrentStatus != "已投递" {
		t.Fatalf("status = %q", item.CurrentStatus)
	}
	if len(item.StatusHistory) == 0 {
		t.Fatal("status history missing")
	}
	if item.StatusUpdateTime == "" {
		t.Fatal("status update time missing")
	}
}

func TestUpdateStatusAppendsHistoryAndDeleteCleansRecord(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	id, err := st.CreateApplication(context.Background(), CreateApplicationInput{CompanyName: "状态公司", PositionName: "产品"})
	if err != nil {
		t.Fatal(err)
	}
	err = st.UpdateApplication(context.Background(), id, UpdateApplicationInput{
		CurrentStatus: "测评", StageState: "已完成，等待结果", NextAction: "等待通知", Source: "内推", Category: "产品", Priority: 2,
	})
	if err != nil {
		t.Fatal(err)
	}
	items, err := st.ListApplications(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].CurrentStatus != "测评" || len(items[0].StatusHistory) != 2 {
		t.Fatalf("unexpected updated application: %#v", items)
	}
	if err := st.DeleteApplication(context.Background(), id); err != nil {
		t.Fatal(err)
	}
	items, err = st.ListApplications(context.Background())
	if err != nil || len(items) != 0 {
		t.Fatalf("delete failed: %#v, %v", items, err)
	}
}

func TestParsesV3TextHistory(t *testing.T) {
	events := parseHistory("2026-07-18 23:30: 已投递 → 简历筛选\n2026-07-19 10:00: 简历筛选 → 测评")
	if len(events) != 2 || events[1].From != "简历筛选" || events[1].To != "测评" {
		t.Fatalf("legacy history not parsed: %#v", events)
	}
}

func TestOpenRepairsLegacyResumeColumnShift(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy-resume.db")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	_, err = st.CreateApplication(context.Background(), CreateApplicationInput{
		CompanyName: "字段公司", PositionName: "产品经理", City: "上海", Source: "官网",
		JobLink: "https://example.com/job", Category: "产品", Tags: "AI,校招", JDText: "岗位职责正文",
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.db.Exec(`UPDATE resumes
SET city=jd_text, application_source=upload_time, job_link=version_note,
    job_category=city, tags=application_source, jd_text=job_link,
    upload_time=job_category, version_note=tags`); err != nil {
		t.Fatal(err)
	}
	if err := st.Close(); err != nil {
		t.Fatal(err)
	}

	st, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	items, err := st.ListApplications(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("got %d applications", len(items))
	}
	item := items[0]
	if item.City != "上海" || item.Source != "官网" || item.JobLink != "https://example.com/job" ||
		item.Category != "产品" || item.Tags != "AI,校招" || item.JDText != "岗位职责正文" {
		t.Fatalf("legacy fields not repaired: %+v", item)
	}
}

func TestBackupCreatesConsistentDatabase(t *testing.T) {
	st, err := Open(filepath.Join(t.TempDir(), "source.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	_, err = st.CreateApplication(context.Background(), CreateApplicationInput{CompanyName: "备份公司", PositionName: "测试"})
	if err != nil {
		t.Fatal(err)
	}
	destination := filepath.Join(t.TempDir(), "backup.db")
	if err := st.Backup(context.Background(), destination); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(destination)
	if err != nil || info.Size() == 0 {
		t.Fatalf("backup missing: %v", err)
	}
	backup, err := Open(destination)
	if err != nil {
		t.Fatal(err)
	}
	defer backup.Close()
	items, err := backup.ListApplications(context.Background())
	if err != nil || len(items) != 1 {
		t.Fatalf("backup content: %#v %v", items, err)
	}
}

func TestImportV3SnapshotMapsSharedColumns(t *testing.T) {
	root := t.TempDir()
	sourcePath := filepath.Join(root, "legacy.db")
	source, err := Open(sourcePath)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := source.CreateApplication(context.Background(), CreateApplicationInput{
		CompanyName: "旧版公司", PositionName: "后端", City: "上海", Source: "官网",
		JobLink: "https://example.com/job", JDText: "旧版 JD", CurrentStatus: "测评", Priority: 2,
	}); err != nil {
		t.Fatal(err)
	}
	if err := source.Close(); err != nil {
		t.Fatal(err)
	}

	legacy, err := sql.Open("sqlite3", sourcePath)
	if err != nil {
		t.Fatal(err)
	}
	for _, statement := range []string{
		"ALTER TABLE resumes DROP COLUMN job_category", "ALTER TABLE resumes DROP COLUMN tags",
		"ALTER TABLE applications DROP COLUMN stage_state", "ALTER TABLE applications DROP COLUMN applied_at",
		"ALTER TABLE applications DROP COLUMN application_deadline", "ALTER TABLE applications DROP COLUMN next_action_due_at",
		"ALTER TABLE applications DROP COLUMN last_follow_up_at", "ALTER TABLE job_tasks DROP COLUMN source",
		"ALTER TABLE interviews DROP COLUMN result", "ALTER TABLE interviews DROP COLUMN questions",
		"ALTER TABLE interviews DROP COLUMN weak_points", "ALTER TABLE interviews DROP COLUMN follow_up",
	} {
		if _, err := legacy.Exec(statement); err != nil {
			legacy.Close()
			t.Fatalf("%s: %v", statement, err)
		}
	}
	if _, err := legacy.Exec("PRAGMA user_version=5"); err != nil {
		t.Fatal(err)
	}
	if err := legacy.Close(); err != nil {
		t.Fatal(err)
	}

	target, err := Open(filepath.Join(root, "target.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	if err := target.ImportV3Snapshot(context.Background(), sourcePath); err != nil {
		t.Fatal(err)
	}
	items, err := target.ListApplications(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("items=%#v", items)
	}
	item := items[0]
	if item.CompanyName != "旧版公司" || item.PositionName != "后端" || item.City != "上海" || item.Source != "官网" ||
		item.JobLink != "https://example.com/job" || item.JDText != "旧版 JD" || item.CurrentStatus != "测评" || item.Priority != 2 {
		t.Fatalf("shared columns not preserved: %+v", item)
	}
	if item.StageState != "已完成，等待结果" || item.Category != "" || item.Tags != "" || item.AppliedAt != "" {
		t.Fatalf("new column defaults not applied: %+v", item)
	}
}
