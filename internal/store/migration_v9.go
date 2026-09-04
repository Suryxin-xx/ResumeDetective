package store

import (
	"database/sql"
	"fmt"
)

func ensureInterviewScheduleColumns(db *sql.DB) error {
	rows, err := db.Query("PRAGMA table_info(interviews)")
	if err != nil {
		return err
	}
	columns := make(map[string]bool)
	for rows.Next() {
		var cid, notNull, primaryKey int
		var name, columnType string
		var defaultValue any
		if err := rows.Scan(&cid, &name, &columnType, &notNull, &defaultValue, &primaryKey); err != nil {
			rows.Close()
			return err
		}
		columns[name] = true
	}
	if err := rows.Close(); err != nil {
		return err
	}
	if err := rows.Err(); err != nil {
		return err
	}

	additions := []struct {
		name string
		sql  string
	}{
		{"interview_mode", "ALTER TABLE interviews ADD COLUMN interview_mode TEXT DEFAULT ''"},
		{"meeting_link", "ALTER TABLE interviews ADD COLUMN meeting_link TEXT DEFAULT ''"},
		{"schedule_notes", "ALTER TABLE interviews ADD COLUMN schedule_notes TEXT DEFAULT ''"},
	}
	for _, addition := range additions {
		if columns[addition.name] {
			continue
		}
		if _, err := db.Exec(addition.sql); err != nil {
			return fmt.Errorf("添加 %s: %w", addition.name, err)
		}
	}
	return nil
}
