package migrate

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"testing"

	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
)

func TestImportIfEmptyCopiesDatabaseAndManagedFiles(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "v3")
	if err := os.MkdirAll(filepath.Join(source, "Resumes"), 0o700); err != nil {
		t.Fatal(err)
	}
	sourceStore, err := store.Open(filepath.Join(source, "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	id, err := sourceStore.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "旧公司", PositionName: "后端", ResumePath: "data/Resumes/test.pdf"})
	if err != nil {
		t.Fatal(err)
	}
	if id != 1 {
		t.Fatal(id)
	}
	if err := sourceStore.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "Resumes", "test.pdf"), []byte("%PDF-1.4"), 0o600); err != nil {
		t.Fatal(err)
	}
	target, err := config.Resolve(filepath.Join(root, "v4"))
	if err != nil {
		t.Fatal(err)
	}
	report, err := ImportIfEmpty(context.Background(), target, source)
	if err != nil {
		t.Fatal(err)
	}
	if !report.Imported {
		t.Fatalf("not imported: %#v", report)
	}
	imported, err := store.Open(target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer imported.Close()
	apps, err := imported.ListApplications(context.Background())
	if err != nil || len(apps) != 1 {
		t.Fatalf("apps=%#v err=%v", apps, err)
	}
	if _, err := os.Stat(filepath.Join(target.ResumesDir, "test.pdf")); err != nil {
		t.Fatal(err)
	}
	var version int
	db, err := sql.Open("sqlite3", target.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil || version != store.SchemaVersion {
		t.Fatalf("version=%d err=%v", version, err)
	}
}

func TestOneClickImportKeepsDatabasesSeparate(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "v3")
	if err := os.MkdirAll(filepath.Join(source, "Resumes"), 0o700); err != nil {
		t.Fatal(err)
	}
	legacy, err := store.Open(filepath.Join(source, "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	_, err = legacy.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "原数据公司", PositionName: "算法", ResumePath: "data/Resumes/legacy.pdf"})
	if err != nil {
		t.Fatal(err)
	}
	if err := legacy.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(source, "Resumes", "legacy.pdf"), []byte("%PDF"), 0o600); err != nil {
		t.Fatal(err)
	}
	paths, err := config.Resolve(filepath.Join(root, "v4"))
	if err != nil {
		t.Fatal(err)
	}
	target, err := store.Open(paths.Database)
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	report, err := ImportIntoStore(context.Background(), target, paths, source)
	if err != nil {
		t.Fatal(err)
	}
	if !report.Imported {
		t.Fatalf("report=%#v", report)
	}
	apps, err := target.ListApplications(context.Background())
	if err != nil || len(apps) != 1 {
		t.Fatalf("apps=%#v err=%v", apps, err)
	}
	if _, err := ImportIntoStore(context.Background(), target, paths, source); err == nil {
		t.Fatal("second import should be rejected")
	}
	legacyCheck, err := store.Open(filepath.Join(source, "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer legacyCheck.Close()
	legacyApps, err := legacyCheck.ListApplications(context.Background())
	if err != nil || len(legacyApps) != 1 {
		t.Fatalf("legacy changed: %#v %v", legacyApps, err)
	}
}

func TestInspectAcceptsDirectoryOrDatabasePath(t *testing.T) {
	source := filepath.Join(t.TempDir(), "Python v3 data")
	if err := os.MkdirAll(source, 0o700); err != nil {
		t.Fatal(err)
	}
	legacy, err := store.Open(filepath.Join(source, "data.db"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := legacy.CreateApplication(context.Background(), store.CreateApplicationInput{CompanyName: "路径测试", PositionName: "开发"}); err != nil {
		t.Fatal(err)
	}
	if err := legacy.Close(); err != nil {
		t.Fatal(err)
	}

	for _, input := range []string{source, filepath.Join(source, "data.db"), `"` + source + `"`} {
		status := Inspect(input)
		if !status.Available || status.Applications != 1 || status.SourceDir != source {
			t.Fatalf("input=%q status=%#v", input, status)
		}
	}
}
