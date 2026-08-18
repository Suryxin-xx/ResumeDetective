package store

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"time"
)

type Task struct {
	ID          int64  `json:"id"`
	Title       string `json:"title"`
	DueDate     string `json:"dueDate"`
	Priority    int    `json:"priority"`
	State       string `json:"state"`
	ScopeType   string `json:"scopeType"`
	ScopeID     int64  `json:"scopeId"`
	Notes       string `json:"notes"`
	Source      string `json:"source"`
	CreatedAt   string `json:"createdAt"`
	CompletedAt string `json:"completedAt"`
}

type Interview struct {
	ID            int64  `json:"id"`
	ApplicationID int64  `json:"applicationId"`
	CompanyName   string `json:"companyName"`
	PositionName  string `json:"positionName"`
	Round         string `json:"round"`
	InterviewTime string `json:"interviewTime"`
	Summary       string `json:"summary"`
	Result        string `json:"result"`
	Questions     string `json:"questions"`
	WeakPoints    string `json:"weakPoints"`
	FollowUp      string `json:"followUp"`
	CreatedAt     string `json:"createdAt"`
}

type CreateTaskInput struct {
	Title    string `json:"title"`
	DueDate  string `json:"dueDate"`
	Priority int    `json:"priority"`
	Notes    string `json:"notes"`
}

type CreateInterviewInput struct {
	ApplicationID int64  `json:"applicationId"`
	Round         string `json:"round"`
	InterviewTime string `json:"interviewTime"`
	Summary       string `json:"summary"`
	Result        string `json:"result"`
	Questions     string `json:"questions"`
	WeakPoints    string `json:"weakPoints"`
	FollowUp      string `json:"followUp"`
}

func (s *Store) ListTasks(ctx context.Context) ([]Task, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT id,title,COALESCE(due_date,''),priority,state,COALESCE(scope_type,''),COALESCE(scope_id,0),COALESCE(notes,''),COALESCE(source,''),COALESCE(created_at,''),COALESCE(completed_at,'') FROM job_tasks ORDER BY CASE state WHEN 'open' THEN 0 ELSE 1 END, CASE WHEN due_date='' THEN 1 ELSE 0 END,due_date,priority DESC,id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Task{}
	for rows.Next() {
		var item Task
		if err := rows.Scan(&item.ID, &item.Title, &item.DueDate, &item.Priority, &item.State, &item.ScopeType, &item.ScopeID, &item.Notes, &item.Source, &item.CreatedAt, &item.CompletedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) CreateTask(ctx context.Context, in CreateTaskInput) (int64, error) {
	in.Title = strings.TrimSpace(in.Title)
	if in.Title == "" {
		return 0, errors.New("任务名称不能为空")
	}
	if in.Priority < 0 || in.Priority > 5 {
		return 0, errors.New("优先级必须在 0 到 5 之间")
	}
	result, err := s.db.ExecContext(ctx, `INSERT INTO job_tasks(title,due_date,priority,state,notes,source,created_at) VALUES(?,?,?,'open',?,'manual',?)`, in.Title, strings.TrimSpace(in.DueDate), in.Priority, strings.TrimSpace(in.Notes), time.Now().Format(time.RFC3339))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

func (s *Store) SetTaskState(ctx context.Context, id int64, state string) error {
	if state != "open" && state != "done" {
		return errors.New("无效的任务状态")
	}
	completed := any(nil)
	if state == "done" {
		completed = time.Now().Format(time.RFC3339)
	}
	result, err := s.db.ExecContext(ctx, "UPDATE job_tasks SET state=?,completed_at=? WHERE id=?", state, completed, id)
	if err != nil {
		return err
	}
	changed, _ := result.RowsAffected()
	if changed == 0 {
		return errors.New("任务不存在")
	}
	return nil
}

func (s *Store) DeleteTask(ctx context.Context, id int64) error {
	result, err := s.db.ExecContext(ctx, "DELETE FROM job_tasks WHERE id=? AND source<>'application_next_action'", id)
	if err != nil {
		return err
	}
	changed, _ := result.RowsAffected()
	if changed == 0 {
		return errors.New("岗位联动任务需在投递管理中修改，或任务不存在")
	}
	return nil
}

func (s *Store) ListInterviews(ctx context.Context) ([]Interview, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT i.id,i.application_id,r.company_name,r.position_name,i.round,COALESCE(i.interview_time,''),COALESCE(i.summary,''),i.result,COALESCE(i.questions,''),COALESCE(i.weak_points,''),COALESCE(i.follow_up,''),COALESCE(i.created_at,'') FROM interviews i JOIN applications a ON a.id=i.application_id JOIN resumes r ON r.id=a.resume_id ORDER BY CASE WHEN i.interview_time='' THEN 1 ELSE 0 END,i.interview_time DESC,i.id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Interview{}
	for rows.Next() {
		var item Interview
		if err := rows.Scan(&item.ID, &item.ApplicationID, &item.CompanyName, &item.PositionName, &item.Round, &item.InterviewTime, &item.Summary, &item.Result, &item.Questions, &item.WeakPoints, &item.FollowUp, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) CreateInterview(ctx context.Context, in CreateInterviewInput) (int64, error) {
	if in.ApplicationID < 1 {
		return 0, errors.New("请选择对应岗位")
	}
	if strings.TrimSpace(in.Round) == "" {
		in.Round = "一面"
	}
	if strings.TrimSpace(in.Result) == "" {
		in.Result = "待确认"
	}
	var exists int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM applications WHERE id=?", in.ApplicationID).Scan(&exists); err != nil {
		return 0, err
	}
	if exists == 0 {
		return 0, errors.New("对应岗位不存在")
	}
	result, err := s.db.ExecContext(ctx, `INSERT INTO interviews(application_id,round,interview_time,summary,result,questions,weak_points,follow_up,created_at) VALUES(?,?,?,?,?,?,?,?,?)`, in.ApplicationID, strings.TrimSpace(in.Round), strings.TrimSpace(in.InterviewTime), strings.TrimSpace(in.Summary), strings.TrimSpace(in.Result), strings.TrimSpace(in.Questions), strings.TrimSpace(in.WeakPoints), strings.TrimSpace(in.FollowUp), time.Now().Format(time.RFC3339))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

func (s *Store) UpdateInterview(ctx context.Context, id int64, in CreateInterviewInput) error {
	if id < 1 {
		return errors.New("面试记录不存在")
	}
	if in.ApplicationID < 1 {
		return errors.New("请选择对应岗位")
	}
	if strings.TrimSpace(in.Round) == "" {
		in.Round = "一面"
	}
	if strings.TrimSpace(in.Result) == "" {
		in.Result = "待确认"
	}
	var applicationExists int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM applications WHERE id=?", in.ApplicationID).Scan(&applicationExists); err != nil {
		return err
	}
	if applicationExists == 0 {
		return errors.New("对应岗位不存在")
	}
	result, err := s.db.ExecContext(ctx, `UPDATE interviews SET application_id=?,round=?,interview_time=?,summary=?,result=?,questions=?,weak_points=?,follow_up=? WHERE id=?`, in.ApplicationID, strings.TrimSpace(in.Round), strings.TrimSpace(in.InterviewTime), strings.TrimSpace(in.Summary), strings.TrimSpace(in.Result), strings.TrimSpace(in.Questions), strings.TrimSpace(in.WeakPoints), strings.TrimSpace(in.FollowUp), id)
	if err != nil {
		return err
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if changed == 0 {
		return errors.New("面试记录不存在")
	}
	return nil
}

func (s *Store) DeleteInterview(ctx context.Context, id int64) error {
	result, err := s.db.ExecContext(ctx, "DELETE FROM interviews WHERE id=?", id)
	if err != nil {
		return err
	}
	changed, _ := result.RowsAffected()
	if changed == 0 {
		return sql.ErrNoRows
	}
	return nil
}
