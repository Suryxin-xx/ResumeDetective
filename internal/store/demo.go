package store

import (
	"context"
	"errors"
)

var demoTables = map[string]string{
	"interview": "interviews", "task": "job_tasks", "application": "applications",
	"resume": "resumes", "target": "job_targets", "material": "materials", "profile": "profile",
	"offer": "offers",
}

func (s *Store) MarkDemo(ctx context.Context, entityType string, id int64) error {
	if _, ok := demoTables[entityType]; !ok || id < 1 {
		return errors.New("无效的演示数据标记")
	}
	_, err := s.db.ExecContext(ctx, "INSERT OR IGNORE INTO demo_records(entity_type,record_id) VALUES(?,?)", entityType, id)
	return err
}

func (s *Store) HasDemo(ctx context.Context) (bool, error) {
	var count int
	err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM demo_records").Scan(&count)
	return count > 0, err
}

func (s *Store) ClearDemo(ctx context.Context) error {
	demo, err := s.HasDemo(ctx)
	if err != nil || !demo {
		return err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	order := []string{"offer", "interview", "task", "application", "resume", "target", "material", "profile"}
	for _, kind := range order {
		table := demoTables[kind]
		if _, err := tx.ExecContext(ctx, "DELETE FROM "+table+" WHERE id IN (SELECT record_id FROM demo_records WHERE entity_type=?)", kind); err != nil {
			return err
		}
	}
	if _, err := tx.ExecContext(ctx, "DELETE FROM demo_records"); err != nil {
		return err
	}
	return tx.Commit()
}
