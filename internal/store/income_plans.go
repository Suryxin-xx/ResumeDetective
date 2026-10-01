package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

func ensureIncomePlans(db *sql.DB) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.Exec(`CREATE TABLE IF NOT EXISTS income_plans (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, parameters TEXT NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);`); err != nil {
		return err
	}
	for _, column := range []struct{ name, definition string }{
		{"offer_id", "INTEGER REFERENCES offers(id) ON DELETE SET NULL"},
		{"source_updated_at", "TEXT NOT NULL DEFAULT ''"},
	} {
		var found int
		if err = tx.QueryRow("SELECT COUNT(*) FROM pragma_table_info('income_plans') WHERE name=?", column.name).Scan(&found); err != nil {
			return err
		}
		if found == 0 {
			if _, err = tx.Exec("ALTER TABLE income_plans ADD COLUMN " + column.name + " " + column.definition); err != nil {
				return err
			}
		}
	}
	var found int
	if err = tx.QueryRow("SELECT COUNT(*) FROM pragma_table_info('offers') WHERE name='income_settings'").Scan(&found); err != nil {
		return err
	}
	if found == 0 {
		if _, err = tx.Exec("ALTER TABLE offers ADD COLUMN income_settings TEXT NOT NULL DEFAULT ''"); err != nil {
			return err
		}
	}
	if _, err = tx.Exec("PRAGMA user_version = 13"); err != nil {
		return err
	}
	return tx.Commit()
}

type IncomePlan struct {
	ID              int64           `json:"id"`
	Name            string          `json:"name"`
	Parameters      json.RawMessage `json:"parameters"`
	UpdatedAt       string          `json:"updatedAt"`
	OfferID         *int64          `json:"offerId"`
	SourceUpdatedAt string          `json:"sourceUpdatedAt"`
}

func (s *Store) ListIncomePlans(ctx context.Context) ([]IncomePlan, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT id,name,parameters,updated_at,offer_id,source_updated_at FROM income_plans ORDER BY updated_at DESC,id DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []IncomePlan{}
	for rows.Next() {
		var p IncomePlan
		var raw string
		if err := rows.Scan(&p.ID, &p.Name, &raw, &p.UpdatedAt, &p.OfferID, &p.SourceUpdatedAt); err != nil {
			return nil, err
		}
		p.Parameters = json.RawMessage(raw)
		items = append(items, p)
	}
	return items, rows.Err()
}
func (s *Store) SaveIncomePlan(ctx context.Context, p IncomePlan) (int64, error) {
	p.Name = strings.TrimSpace(p.Name)
	if p.ID < 0 || p.Name == "" || len([]rune(p.Name)) > 80 || len(p.Parameters) > 16384 {
		return 0, errors.New("方案名称需为 1–80 字，参数不能过长")
	}
	var params IncomeParameters
	if json.Unmarshal(p.Parameters, &params) != nil || params.Version != 1 {
		return 0, errors.New("收入方案参数无效或版本不受支持")
	}
	if err := validateIncomeParameters(params, false); err != nil {
		return 0, err
	}
	if p.OfferID != nil {
		var found int
		if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM offers WHERE id=?", *p.OfferID).Scan(&found); err != nil {
			return 0, err
		}
		if found == 0 {
			return 0, errors.New("关联的 Offer 不存在，请选择其他 Offer 或独立试算")
		}
	} else {
		p.SourceUpdatedAt = ""
	}
	p.Parameters, _ = json.Marshal(params)
	if p.ID == 0 {
		res, err := s.db.ExecContext(ctx, "INSERT INTO income_plans(name,parameters,offer_id,source_updated_at) VALUES(?,?,?,?)", p.Name, string(p.Parameters), p.OfferID, p.SourceUpdatedAt)
		if err != nil {
			return 0, err
		}
		return res.LastInsertId()
	}
	res, err := s.db.ExecContext(ctx, "UPDATE income_plans SET name=?,parameters=?,offer_id=?,source_updated_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", p.Name, string(p.Parameters), p.OfferID, p.SourceUpdatedAt, p.ID)
	if err != nil {
		return 0, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, err
	}
	if n == 0 {
		return 0, errors.New("方案不存在，请另存为新方案")
	}
	return p.ID, nil
}
func (s *Store) DeleteIncomePlan(ctx context.Context, id int64) error {
	_, err := s.db.ExecContext(ctx, "DELETE FROM income_plans WHERE id=?", id)
	return err
}
