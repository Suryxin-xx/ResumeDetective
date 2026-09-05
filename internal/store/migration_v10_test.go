package store

import (
	"path/filepath"
	"testing"
)

func TestOpenAddsApplicationScheduleColumnsWithoutChangingRows(t *testing.T) {
	path := filepath.Join(t.TempDir(), "v9.db")
	seed, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := seed.db.Exec(`INSERT INTO resumes(id,company_name,position_name,file_path) VALUES(1,'旧公司','旧岗位','');
		INSERT INTO applications(id,resume_id,current_status,stage_state) VALUES(1,1,'测评','已安排');
		ALTER TABLE applications DROP COLUMN stage_time_type;
		ALTER TABLE applications DROP COLUMN stage_scheduled_at;
		ALTER TABLE applications DROP COLUMN stage_completed_at;
		ALTER TABLE applications DROP COLUMN stage_time_note;
		PRAGMA user_version=9;`); err != nil {
		seed.Close()
		t.Fatal(err)
	}
	if err := seed.Close(); err != nil {
		t.Fatal(err)
	}
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	var status, state string
	if err := st.db.QueryRow("SELECT current_status,stage_state FROM applications WHERE id=1").Scan(&status, &state); err != nil {
		t.Fatal(err)
	}
	if status != "测评" || state != "已安排" {
		t.Fatalf("existing row changed: %s / %s", status, state)
	}
	for _, name := range []string{"stage_time_type", "stage_scheduled_at", "stage_completed_at", "stage_time_note"} {
		var count int
		if err := st.db.QueryRow("SELECT COUNT(*) FROM pragma_table_info('applications') WHERE name=?", name).Scan(&count); err != nil || count != 1 {
			t.Fatalf("missing %s: count=%d err=%v", name, count, err)
		}
	}
}
