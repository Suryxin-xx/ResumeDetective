package store

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestOpenAddsInterviewScheduleColumns(t *testing.T) {
	path := filepath.Join(t.TempDir(), "v8.db")
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`CREATE TABLE interviews (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		application_id INTEGER NOT NULL,
		round TEXT NOT NULL DEFAULT '一面',
		interview_time TEXT DEFAULT '',
		summary TEXT DEFAULT '',
		result TEXT DEFAULT '待确认',
		questions TEXT DEFAULT '',
		weak_points TEXT DEFAULT '',
		follow_up TEXT DEFAULT '',
		created_at TEXT DEFAULT ''
	); PRAGMA user_version=8;`); err != nil {
		db.Close()
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	store, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()

	rows, err := store.db.Query("PRAGMA table_info(interviews)")
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	columns := map[string]bool{}
	for rows.Next() {
		var cid, notNull, primaryKey int
		var name, columnType string
		var defaultValue any
		if err := rows.Scan(&cid, &name, &columnType, &notNull, &defaultValue, &primaryKey); err != nil {
			t.Fatal(err)
		}
		columns[name] = true
	}
	for _, name := range []string{"interview_mode", "meeting_link", "schedule_notes"} {
		if !columns[name] {
			t.Fatalf("missing migrated column %s", name)
		}
	}
}
