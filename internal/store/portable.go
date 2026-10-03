package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// InspectPortable never runs migration or creates a missing source database.
func InspectPortable(path string) error {
	db, err := readOnlyDatabase(path)
	if err != nil {
		return err
	}
	defer db.Close()
	var integrity string
	if err := db.QueryRow("PRAGMA quick_check").Scan(&integrity); err != nil || integrity != "ok" {
		return errors.New("数据库完整性检查未通过")
	}
	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return err
	}
	if version < 6 || version > SchemaVersion {
		return fmt.Errorf("仅支持 v4 数据库（结构版本 6–%d），当前为 %d；Python v3 请使用原迁移入口", SchemaVersion, version)
	}
	for _, table := range []string{"applications", "resumes", "interviews", "offers"} {
		var n int
		if err := db.QueryRow("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&n); err != nil || n != 1 {
			return errors.New("不是兼容的 ResumeDetective 数据库")
		}
	}
	return nil
}

func readOnlyDatabase(path string) (*sql.DB, error) {
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() {
		return nil, errors.New("未找到普通数据库文件")
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	// A Windows drive must remain a path, not a URI host (file://E:/...).
	u := url.URL{Path: filepath.ToSlash(abs)}
	return sql.Open("sqlite3", "file:"+u.EscapedPath()+"?mode=ro&_busy_timeout=10000")
}

// SnapshotPortable copies a live source consistently without modifying it.
func SnapshotPortable(ctx context.Context, source, destination string) error {
	if err := InspectPortable(source); err != nil {
		return err
	}
	if _, err := os.Stat(destination); !os.IsNotExist(err) {
		return errors.New("导入目标已存在，拒绝覆盖")
	}
	db, err := readOnlyDatabase(source)
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.ExecContext(ctx, "VACUUM INTO ?", destination)
	return err
}

// RebaseFiles is used only on imported copies. Unknown external links are
// rejected rather than silently pointing into another space.
func (s *Store) RebaseFiles(ctx context.Context, sourceDir, targetDir string) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, table := range []string{"resumes", "application_attachments"} {
		rows, err := tx.QueryContext(ctx, "SELECT id,file_path FROM "+table+" WHERE file_path<>''")
		if err != nil {
			return err
		}
		type ref struct {
			id   int64
			path string
		}
		refs := []ref{}
		for rows.Next() {
			var r ref
			if err := rows.Scan(&r.id, &r.path); err != nil {
				rows.Close()
				return err
			}
			refs = append(refs, r)
		}
		err = rows.Err()
		rows.Close()
		if err != nil {
			return err
		}
		for _, r := range refs {
			rel, err := ManagedRelative(sourceDir, r.path)
			if err != nil {
				return err
			}
			path := filepath.Join(targetDir, rel)
			if info, err := os.Stat(path); err != nil || !info.Mode().IsRegular() {
				return fmt.Errorf("简历或附件缺失：%s", rel)
			}
			if _, err := tx.ExecContext(ctx, "UPDATE "+table+" SET file_path=? WHERE id=?", path, r.id); err != nil {
				return err
			}
		}
	}
	return tx.Commit()
}

func ManagedRelative(base, path string) (string, error) {
	if !filepath.IsAbs(path) {
		path = filepath.Join(base, path)
	}
	rel, err := filepath.Rel(base, path)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", errors.New("存在数据目录外的简历/附件，请先收纳到本空间后再导入或备份")
	}
	parts := strings.Split(filepath.ToSlash(rel), "/")
	if len(parts) < 2 || (parts[0] != "resumes" && parts[0] != "attachments") {
		return "", errors.New("简历/附件路径不属于受管目录")
	}
	return rel, nil
}

func (s *Store) FileReferences(ctx context.Context) ([]string, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT file_path FROM resumes WHERE file_path<>'' UNION SELECT file_path FROM application_attachments WHERE file_path<>''")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []string{}
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return nil, err
		}
		result = append(result, p)
	}
	return result, rows.Err()
}
