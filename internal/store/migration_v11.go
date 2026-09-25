package store

import "database/sql"

func ensureOfferTaxColumn(db *sql.DB) error {
	var exists int
	if err := db.QueryRow("SELECT COUNT(*) FROM pragma_table_info('offers') WHERE name='tax_settings'").Scan(&exists); err != nil {
		return err
	}
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if exists == 0 {
		if _, err := tx.Exec("ALTER TABLE offers ADD COLUMN tax_settings TEXT DEFAULT ''"); err != nil {
			return err
		}
	}
	return tx.Commit()
}
