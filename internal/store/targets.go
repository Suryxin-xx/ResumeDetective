package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"
)

var targetStatuses = map[string]bool{"待研究": true, "待投递": true, "已投递": true, "暂不考虑": true}

type JobTarget struct {
	ID           int64  `json:"id"`
	CompanyName  string `json:"companyName"`
	PositionName string `json:"positionName"`
	JDText       string `json:"jdText"`
	JDLink       string `json:"jdLink"`
	City         string `json:"city"`
	Status       string `json:"status"`
	Notes        string `json:"notes"`
	Priority     int    `json:"priority"`
	CreatedAt    string `json:"createdAt"`
	UpdatedAt    string `json:"updatedAt"`
}

type JobTargetInput struct {
	CompanyName  string `json:"companyName"`
	PositionName string `json:"positionName"`
	JDText       string `json:"jdText"`
	JDLink       string `json:"jdLink"`
	City         string `json:"city"`
	Status       string `json:"status"`
	Notes        string `json:"notes"`
	Priority     int    `json:"priority"`
}

type ConvertTargetInput struct {
	Source     string `json:"source"`
	Category   string `json:"category"`
	Tags       string `json:"tags"`
	ResumePath string `json:"resumePath"`
	AppliedAt  string `json:"appliedAt"`
}

func (s *Store) ListJobTargets(ctx context.Context) ([]JobTarget, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id,company_name,position_name,COALESCE(jd_text,''),COALESCE(jd_link,''),COALESCE(city,''),status,COALESCE(notes,''),priority,COALESCE(created_at,''),COALESCE(updated_at,'') FROM job_targets ORDER BY CASE status WHEN '待投递' THEN 0 WHEN '待研究' THEN 1 WHEN '已投递' THEN 2 ELSE 3 END,priority DESC,updated_at DESC,id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []JobTarget{}
	for rows.Next() {
		var item JobTarget
		if err := rows.Scan(&item.ID, &item.CompanyName, &item.PositionName, &item.JDText, &item.JDLink, &item.City, &item.Status, &item.Notes, &item.Priority, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) CreateJobTarget(ctx context.Context, in JobTargetInput) (int64, error) {
	if err := validateTarget(&in); err != nil {
		return 0, err
	}
	now := time.Now().Format(time.RFC3339)
	result, err := s.db.ExecContext(ctx, `INSERT INTO job_targets(company_name,position_name,jd_text,jd_link,city,status,notes,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)`, in.CompanyName, in.PositionName, in.JDText, in.JDLink, in.City, in.Status, in.Notes, in.Priority, now, now)
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

func (s *Store) UpdateJobTarget(ctx context.Context, id int64, in JobTargetInput) error {
	if id < 1 {
		return errors.New("无效的意向编号")
	}
	if err := validateTarget(&in); err != nil {
		return err
	}
	result, err := s.db.ExecContext(ctx, `UPDATE job_targets SET company_name=?,position_name=?,jd_text=?,jd_link=?,city=?,status=?,notes=?,priority=?,updated_at=? WHERE id=?`, in.CompanyName, in.PositionName, in.JDText, in.JDLink, in.City, in.Status, in.Notes, in.Priority, time.Now().Format(time.RFC3339), id)
	if err != nil {
		return err
	}
	changed, _ := result.RowsAffected()
	if changed == 0 {
		return errors.New("意向记录不存在")
	}
	return nil
}

func (s *Store) DeleteJobTarget(ctx context.Context, id int64) error {
	result, err := s.db.ExecContext(ctx, "DELETE FROM job_targets WHERE id=?", id)
	if err != nil {
		return err
	}
	changed, _ := result.RowsAffected()
	if changed == 0 {
		return errors.New("意向记录不存在")
	}
	return nil
}

func (s *Store) ConvertJobTarget(ctx context.Context, id int64, in ConvertTargetInput) (int64, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	var target JobTarget
	if err := tx.QueryRowContext(ctx, `SELECT id,company_name,position_name,COALESCE(jd_text,''),COALESCE(jd_link,''),COALESCE(city,''),status,COALESCE(notes,''),priority,COALESCE(created_at,''),COALESCE(updated_at,'') FROM job_targets WHERE id=?`, id).Scan(&target.ID, &target.CompanyName, &target.PositionName, &target.JDText, &target.JDLink, &target.City, &target.Status, &target.Notes, &target.Priority, &target.CreatedAt, &target.UpdatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return 0, errors.New("意向记录不存在")
		}
		return 0, err
	}
	if target.Status == "已投递" {
		return 0, errors.New("该意向已经转为投递")
	}
	now := time.Now().Format(time.RFC3339)
	appliedAt := strings.TrimSpace(in.AppliedAt)
	if appliedAt == "" {
		appliedAt = now[:10]
	}
	resumeResult, err := tx.ExecContext(ctx, `INSERT INTO resumes(company_name,position_name,file_path,city,application_source,job_link,job_category,tags,jd_text,upload_time) VALUES(?,?,?,?,?,?,?,?,?,?)`, target.CompanyName, target.PositionName, strings.TrimSpace(in.ResumePath), target.City, strings.TrimSpace(in.Source), target.JDLink, strings.TrimSpace(in.Category), strings.TrimSpace(in.Tags), target.JDText, now)
	if err != nil {
		return 0, err
	}
	resumeID, err := resumeResult.LastInsertId()
	if err != nil {
		return 0, err
	}
	history, _ := json.Marshal([]StatusEvent{{To: "已投递", Time: now, Note: "由意向清单转为投递"}})
	applicationResult, err := tx.ExecContext(ctx, `INSERT INTO applications(resume_id,current_status,stage_state,priority,status_update_time,applied_at,status_history) VALUES(?,'已投递','已完成，等待结果',?,?,?,?)`, resumeID, target.Priority, now, appliedAt, string(history))
	if err != nil {
		return 0, err
	}
	applicationID, err := applicationResult.LastInsertId()
	if err != nil {
		return 0, err
	}
	if _, err := tx.ExecContext(ctx, `UPDATE job_targets SET status='已投递',updated_at=?,notes=? WHERE id=?`, now, appendConversionNote(target.Notes, applicationID), id); err != nil {
		return 0, err
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return applicationID, nil
}

func validateTarget(in *JobTargetInput) error {
	in.CompanyName = strings.TrimSpace(in.CompanyName)
	in.PositionName = strings.TrimSpace(in.PositionName)
	in.JDLink = strings.TrimSpace(in.JDLink)
	in.City = strings.TrimSpace(in.City)
	in.Status = strings.TrimSpace(in.Status)
	in.Notes = strings.TrimSpace(in.Notes)
	if in.CompanyName == "" || in.PositionName == "" {
		return errors.New("公司和岗位不能为空")
	}
	if in.Status == "" {
		in.Status = "待研究"
	}
	if !targetStatuses[in.Status] {
		return errors.New("无效的意向状态")
	}
	if in.Priority < 0 || in.Priority > 5 {
		return errors.New("优先级必须在 0 到 5 之间")
	}
	return nil
}

func appendConversionNote(notes string, applicationID int64) string {
	line := "已转为投递 #" + strconv.FormatInt(applicationID, 10)
	if strings.TrimSpace(notes) == "" {
		return line
	}
	return strings.TrimSpace(notes) + "\n" + line
}
