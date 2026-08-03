package store

import (
	"context"
	"database/sql"
	"errors"
	"strings"
)

type Profile struct {
	ID           int64  `json:"id"`
	FullName     string `json:"fullName"`
	Email        string `json:"email"`
	City         string `json:"city"`
	Education    string `json:"education"`
	School       string `json:"school"`
	Major        string `json:"major"`
	TargetRole   string `json:"targetRole"`
	Summary      string `json:"summary"`
	GitHubURL    string `json:"githubUrl"`
	PortfolioURL string `json:"portfolioUrl"`
	UpdatedAt    string `json:"updatedAt"`
}

type Material struct {
	ID           int64  `json:"id"`
	MaterialType string `json:"materialType"`
	Title        string `json:"title"`
	Content      string `json:"content"`
	Tags         string `json:"tags"`
	StartTime    string `json:"startTime"`
	EndTime      string `json:"endTime"`
	CreatedAt    string `json:"createdAt"`
}

type MaterialInput struct {
	MaterialType string `json:"materialType"`
	Title        string `json:"title"`
	Content      string `json:"content"`
	Tags         string `json:"tags"`
	StartTime    string `json:"startTime"`
	EndTime      string `json:"endTime"`
}

func (s *Store) GetProfile(ctx context.Context) (Profile, error) {
	var p Profile
	err := s.db.QueryRowContext(ctx, `SELECT id,full_name,email,city,education,school,major,target_role,summary,github_url,portfolio_url,COALESCE(updated_at,'') FROM profile ORDER BY id LIMIT 1`).Scan(
		&p.ID, &p.FullName, &p.Email, &p.City, &p.Education, &p.School, &p.Major, &p.TargetRole, &p.Summary, &p.GitHubURL, &p.PortfolioURL, &p.UpdatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Profile{}, nil
	}
	return p, err
}

func (s *Store) SaveProfile(ctx context.Context, p Profile) error {
	if p.ID > 0 {
		_, err := s.db.ExecContext(ctx, `UPDATE profile SET full_name=?,email=?,city=?,education=?,school=?,major=?,target_role=?,summary=?,github_url=?,portfolio_url=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`,
			strings.TrimSpace(p.FullName), strings.TrimSpace(p.Email), strings.TrimSpace(p.City), strings.TrimSpace(p.Education), strings.TrimSpace(p.School), strings.TrimSpace(p.Major), strings.TrimSpace(p.TargetRole), strings.TrimSpace(p.Summary), strings.TrimSpace(p.GitHubURL), strings.TrimSpace(p.PortfolioURL), p.ID)
		return err
	}
	_, err := s.db.ExecContext(ctx, `INSERT INTO profile(full_name,email,city,education,school,major,target_role,summary,github_url,portfolio_url,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)`,
		strings.TrimSpace(p.FullName), strings.TrimSpace(p.Email), strings.TrimSpace(p.City), strings.TrimSpace(p.Education), strings.TrimSpace(p.School), strings.TrimSpace(p.Major), strings.TrimSpace(p.TargetRole), strings.TrimSpace(p.Summary), strings.TrimSpace(p.GitHubURL), strings.TrimSpace(p.PortfolioURL))
	return err
}

func (s *Store) ListMaterials(ctx context.Context) ([]Material, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id,COALESCE(material_type,''),COALESCE(title,''),content,COALESCE(tags,''),COALESCE(start_time,''),COALESCE(end_time,''),COALESCE(created_at,'') FROM materials ORDER BY created_at DESC,id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Material{}
	for rows.Next() {
		var item Material
		if err := rows.Scan(&item.ID, &item.MaterialType, &item.Title, &item.Content, &item.Tags, &item.StartTime, &item.EndTime, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func validateMaterial(in MaterialInput) (MaterialInput, error) {
	in.MaterialType = strings.TrimSpace(in.MaterialType)
	in.Title = strings.TrimSpace(in.Title)
	in.Content = strings.TrimSpace(in.Content)
	in.Tags = strings.TrimSpace(in.Tags)
	if in.MaterialType == "" {
		in.MaterialType = "项目经历"
	}
	if in.Title == "" || in.Content == "" {
		return in, errors.New("经历标题和内容不能为空")
	}
	return in, nil
}

func (s *Store) CreateMaterial(ctx context.Context, in MaterialInput) (int64, error) {
	in, err := validateMaterial(in)
	if err != nil {
		return 0, err
	}
	result, err := s.db.ExecContext(ctx, `INSERT INTO materials(material_type,title,content,tags,start_time,end_time) VALUES(?,?,?,?,?,?)`, in.MaterialType, in.Title, in.Content, in.Tags, strings.TrimSpace(in.StartTime), strings.TrimSpace(in.EndTime))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}
func (s *Store) UpdateMaterial(ctx context.Context, id int64, in MaterialInput) error {
	in, err := validateMaterial(in)
	if err != nil {
		return err
	}
	result, err := s.db.ExecContext(ctx, `UPDATE materials SET material_type=?,title=?,content=?,tags=?,start_time=?,end_time=? WHERE id=?`, in.MaterialType, in.Title, in.Content, in.Tags, strings.TrimSpace(in.StartTime), strings.TrimSpace(in.EndTime), id)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return errors.New("经历记录不存在")
	}
	return nil
}
func (s *Store) DeleteMaterial(ctx context.Context, id int64) error {
	result, err := s.db.ExecContext(ctx, `DELETE FROM materials WHERE id=?`, id)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return errors.New("经历记录不存在")
	}
	return nil
}
