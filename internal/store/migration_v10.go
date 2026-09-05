package store

import (
	"database/sql"
	"fmt"
)

func ensureApplicationScheduleColumns(db *sql.DB) error {
	rows, err := db.Query("PRAGMA table_info(applications)")
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
	additions := []struct{ name, sql string }{
		{"stage_time_type", "ALTER TABLE applications ADD COLUMN stage_time_type TEXT DEFAULT ''"},
		{"stage_scheduled_at", "ALTER TABLE applications ADD COLUMN stage_scheduled_at TEXT DEFAULT ''"},
		{"stage_completed_at", "ALTER TABLE applications ADD COLUMN stage_completed_at TEXT DEFAULT ''"},
		{"stage_time_note", "ALTER TABLE applications ADD COLUMN stage_time_note TEXT DEFAULT ''"},
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
