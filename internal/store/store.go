package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Store struct {
	db      *sql.DB
	dataDir string
}

var (
	applicationStatuses = map[string]bool{
		"已投递": true, "简历筛选": true, "测评": true, "AI 面试": true,
		"笔试": true, "业务面试": true, "HR 面": true, "Offer": true, "终止": true,
	}
	stageStates       = map[string]bool{"待处理": true, "已安排": true, "已完成，等待结果": true, "已完成": true}
	legacyHistoryLine = regexp.MustCompile(`^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}):\s*(.+?)\s*→\s*(.+?)$`)
)

type StatusEvent struct {
	From string `json:"from,omitempty"`
	To   string `json:"to"`
	Time string `json:"time"`
	Note string `json:"note,omitempty"`
}

type Application struct {
	ID                  int64         `json:"id"`
	ResumeID            int64         `json:"resumeId"`
	CompanyName         string        `json:"companyName"`
	PositionName        string        `json:"positionName"`
	City                string        `json:"city"`
	Source              string        `json:"source"`
	JobLink             string        `json:"jobLink"`
	Category            string        `json:"category"`
	Tags                string        `json:"tags"`
	JDText              string        `json:"jdText"`
	ResumePath          string        `json:"resumePath"`
	CurrentStatus       string        `json:"currentStatus"`
	StageState          string        `json:"stageState"`
	Priority            int           `json:"priority"`
	StatusUpdateTime    string        `json:"statusUpdateTime"`
	NextAction          string        `json:"nextAction"`
	AppliedAt           string        `json:"appliedAt"`
	ApplicationDeadline string        `json:"applicationDeadline"`
	NextActionDueAt     string        `json:"nextActionDueAt"`
	LastFollowUpAt      string        `json:"lastFollowUpAt"`
	StatusHistory       []StatusEvent `json:"statusHistory"`
}

type CreateApplicationInput struct {
	CompanyName         string `json:"companyName"`
	PositionName        string `json:"positionName"`
	City                string `json:"city"`
	Source              string `json:"source"`
	JobLink             string `json:"jobLink"`
	Category            string `json:"category"`
	Tags                string `json:"tags"`
	JDText              string `json:"jdText"`
	ResumePath          string `json:"resumePath"`
	Priority            int    `json:"priority"`
	CurrentStatus       string `json:"currentStatus"`
	StageState          string `json:"stageState"`
	NextAction          string `json:"nextAction"`
	AppliedAt           string `json:"appliedAt"`
	ApplicationDeadline string `json:"applicationDeadline"`
	NextActionDueAt     string `json:"nextActionDueAt"`
	LastFollowUpAt      string `json:"lastFollowUpAt"`
}

type UpdateApplicationInput struct {
	CurrentStatus       string `json:"currentStatus"`
	StageState          string `json:"stageState"`
	NextAction          string `json:"nextAction"`
	City                string `json:"city"`
	Source              string `json:"source"`
	JobLink             string `json:"jobLink"`
	Category            string `json:"category"`
	Tags                string `json:"tags"`
	JDText              string `json:"jdText"`
	Priority            int    `json:"priority"`
	AppliedAt           string `json:"appliedAt"`
	ApplicationDeadline string `json:"applicationDeadline"`
	NextActionDueAt     string `json:"nextActionDueAt"`
	LastFollowUpAt      string `json:"lastFollowUpAt"`
}

type Dashboard struct {
	Total       int            `json:"total"`
	Active      int            `json:"active"`
	Interview   int            `json:"interview"`
	Offers      int            `json:"offers"`
	OpenTasks   int            `json:"openTasks"`
	StageCounts map[string]int `json:"stageCounts"`
	Demo        bool           `json:"demo"`
}

func Open(path string) (*Store, error) {
	dsn := fmt.Sprintf("file:%s?_foreign_keys=on&_busy_timeout=10000&_journal_mode=WAL&_synchronous=NORMAL", path)
	db, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		db.Close()
		return nil, err
	}
	if version > SchemaVersion {
		db.Close()
		return nil, fmt.Errorf("数据库版本 %d 高于当前支持的 %d", version, SchemaVersion)
	}
	if _, err := db.Exec(schemaV6); err != nil {
		db.Close()
		return nil, fmt.Errorf("初始化数据库: %w", err)
	}
	if err := repairLegacyResumeRows(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("修复旧版简历字段: %w", err)
	}
	if err := repairLegacyTargetRows(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("修复旧版意向数据: %w", err)
	}
	return &Store{db: db, dataDir: filepath.Dir(path)}, nil
}

func repairLegacyResumeRows(db *sql.DB) error {
	// Some early v3 databases had city/source/link/category/tags appended after
	// jd_text/upload_time/version_note. The first v4 importer copied SELECT *
	// into the new column order, shifting eight fields while keeping the data.
	// A timestamp in application_source combined with a non-timestamp
	// upload_time uniquely identifies those migrated rows.
	_, err := db.Exec(`UPDATE resumes
SET city=COALESCE(job_category,''),
    application_source=COALESCE(tags,''),
    job_link=COALESCE(jd_text,''),
    job_category=COALESCE(CAST(upload_time AS TEXT),''),
    tags=COALESCE(version_note,''),
    jd_text=COALESCE(city,''),
    upload_time=application_source,
    version_note=job_link
WHERE CAST(application_source AS TEXT) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]?[0-9][0-9]:[0-9][0-9]:[0-9][0-9]*'
  AND COALESCE(CAST(upload_time AS TEXT),'') NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]?[0-9][0-9]:[0-9][0-9]:[0-9][0-9]*'`)
	return err
}

func repairLegacyTargetRows(db *sql.DB) error {
	// An early v3→v4 copier inserted the old ten-column layout with SELECT *.
	// SQLite then placed created_at/updated_at strings in priority/sort_order.
	_, err := db.Exec(repairLegacyTargetsSQL)
	return err
}

const repairLegacyTargetsSQL = `UPDATE job_targets
SET created_at=CAST(priority AS TEXT), updated_at=CAST(sort_order AS TEXT), priority=0, sort_order=0
WHERE typeof(priority)='text' AND priority GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'
  AND typeof(created_at) IN ('integer','real')`

func (s *Store) Close() error { return s.db.Close() }

func (s *Store) ListApplications(ctx context.Context) ([]Application, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT a.id, a.resume_id, r.company_name, r.position_name, r.city, r.application_source,
       r.job_link, r.job_category, r.tags, COALESCE(r.jd_text,''), r.file_path,
       a.current_status, a.stage_state, a.priority, COALESCE(a.status_update_time,''),
       COALESCE(a.next_action,''), COALESCE(a.applied_at,''), COALESCE(a.application_deadline,''),
       COALESCE(a.next_action_due_at,''), COALESCE(a.last_follow_up_at,''), COALESCE(a.status_history,'')
FROM applications a JOIN resumes r ON r.id=a.resume_id
ORDER BY CASE WHEN a.current_status IN ('终止','已终止','未通过','主动放弃','流程结束') THEN 1 ELSE 0 END,
         a.priority DESC, a.status_update_time DESC, a.id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]Application, 0)
	for rows.Next() {
		var item Application
		var history string
		if err := rows.Scan(&item.ID, &item.ResumeID, &item.CompanyName, &item.PositionName, &item.City, &item.Source,
			&item.JobLink, &item.Category, &item.Tags, &item.JDText, &item.ResumePath, &item.CurrentStatus,
			&item.StageState, &item.Priority, &item.StatusUpdateTime, &item.NextAction, &item.AppliedAt,
			&item.ApplicationDeadline, &item.NextActionDueAt, &item.LastFollowUpAt, &history); err != nil {
			return nil, err
		}
		item.StatusHistory = parseHistory(history)
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) GetApplication(ctx context.Context, id int64) (Application, error) {
	items, err := s.ListApplications(ctx)
	if err != nil {
		return Application{}, err
	}
	for _, item := range items {
		if item.ID == id {
			return item, nil
		}
	}
	return Application{}, errors.New("投递记录不存在")
}

func (s *Store) CreateApplication(ctx context.Context, in CreateApplicationInput) (int64, error) {
	in.CompanyName = strings.TrimSpace(in.CompanyName)
	in.PositionName = strings.TrimSpace(in.PositionName)
	if in.CompanyName == "" || in.PositionName == "" {
		return 0, errors.New("公司和岗位不能为空")
	}
	if in.CurrentStatus == "" {
		in.CurrentStatus = "已投递"
	}
	if in.StageState == "" {
		in.StageState = "已完成，等待结果"
	}
	if !applicationStatuses[in.CurrentStatus] {
		return 0, errors.New("无效的招聘阶段")
	}
	if !stageStates[in.StageState] {
		return 0, errors.New("无效的阶段状态")
	}
	if in.Priority < 0 || in.Priority > 5 {
		return 0, errors.New("优先级必须在 0 到 5 之间")
	}
	now := time.Now().Format(time.RFC3339)
	if strings.TrimSpace(in.AppliedAt) == "" {
		in.AppliedAt = now[:10]
	}
	history, _ := json.Marshal([]StatusEvent{{To: in.CurrentStatus, Time: now, Note: "创建投递"}})
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	res, err := tx.ExecContext(ctx, `INSERT INTO resumes
(company_name,position_name,file_path,city,application_source,job_link,job_category,tags,jd_text,upload_time)
VALUES(?,?,?,?,?,?,?,?,?,?)`, in.CompanyName, in.PositionName, in.ResumePath, strings.TrimSpace(in.City),
		strings.TrimSpace(in.Source), strings.TrimSpace(in.JobLink), strings.TrimSpace(in.Category), strings.TrimSpace(in.Tags), in.JDText, now)
	if err != nil {
		return 0, err
	}
	resumeID, err := res.LastInsertId()
	if err != nil {
		return 0, err
	}
	res, err = tx.ExecContext(ctx, `INSERT INTO applications
(resume_id,current_status,stage_state,priority,status_update_time,applied_at,application_deadline,next_action,next_action_due_at,last_follow_up_at,status_history)
VALUES(?,?,?,?,?,?,?,?,?,?,?)`, resumeID, in.CurrentStatus, in.StageState, in.Priority, now, strings.TrimSpace(in.AppliedAt),
		strings.TrimSpace(in.ApplicationDeadline), strings.TrimSpace(in.NextAction), strings.TrimSpace(in.NextActionDueAt), strings.TrimSpace(in.LastFollowUpAt), string(history))
	if err != nil {
		return 0, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return 0, err
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return id, nil
}

func (s *Store) UpdateApplication(ctx context.Context, id int64, in UpdateApplicationInput) error {
	if id < 1 {
		return errors.New("无效的投递编号")
	}
	if !applicationStatuses[in.CurrentStatus] {
		return errors.New("无效的招聘阶段")
	}
	if !stageStates[in.StageState] {
		return errors.New("无效的阶段状态")
	}
	if in.Priority < 0 || in.Priority > 5 {
		return errors.New("优先级必须在 0 到 5 之间")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var resumeID int64
	var oldStatus, oldStageState, oldStatusUpdateTime, historyRaw string
	if err := tx.QueryRowContext(ctx, "SELECT resume_id,current_status,stage_state,COALESCE(status_update_time,''),COALESCE(status_history,'') FROM applications WHERE id=?", id).Scan(&resumeID, &oldStatus, &oldStageState, &oldStatusUpdateTime, &historyRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return errors.New("投递记录不存在")
		}
		return err
	}
	now := time.Now().Format(time.RFC3339)
	statusUpdateTime := oldStatusUpdateTime
	if oldStatus != in.CurrentStatus || oldStageState != in.StageState || statusUpdateTime == "" {
		statusUpdateTime = now
	}
	history := parseHistory(historyRaw)
	if oldStatus != in.CurrentStatus {
		history = append(history, StatusEvent{From: oldStatus, To: in.CurrentStatus, Time: now, Note: "手动更新"})
	}
	historyJSON, err := json.Marshal(history)
	if err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `UPDATE resumes SET city=?,application_source=?,job_link=?,job_category=?,tags=?,jd_text=? WHERE id=?`,
		strings.TrimSpace(in.City), strings.TrimSpace(in.Source), strings.TrimSpace(in.JobLink), strings.TrimSpace(in.Category), strings.TrimSpace(in.Tags), in.JDText, resumeID); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `UPDATE applications SET current_status=?,stage_state=?,next_action=?,priority=?,applied_at=?,application_deadline=?,next_action_due_at=?,last_follow_up_at=?,status_update_time=?,status_history=? WHERE id=?`,
		in.CurrentStatus, in.StageState, strings.TrimSpace(in.NextAction), in.Priority, strings.TrimSpace(in.AppliedAt), strings.TrimSpace(in.ApplicationDeadline),
		strings.TrimSpace(in.NextActionDueAt), strings.TrimSpace(in.LastFollowUpAt), statusUpdateTime, string(historyJSON), id); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *Store) DeleteApplication(ctx context.Context, id int64) error {
	if id < 1 {
		return errors.New("无效的投递编号")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var resumeID int64
	if err := tx.QueryRowContext(ctx, "SELECT resume_id FROM applications WHERE id=?", id).Scan(&resumeID); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return errors.New("投递记录不存在")
		}
		return err
	}
	if _, err := tx.ExecContext(ctx, "DELETE FROM applications WHERE id=?", id); err != nil {
		return err
	}
	var references int
	if err := tx.QueryRowContext(ctx, "SELECT COUNT(*) FROM applications WHERE resume_id=?", resumeID).Scan(&references); err != nil {
		return err
	}
	if references == 0 {
		if _, err := tx.ExecContext(ctx, "DELETE FROM resumes WHERE id=?", resumeID); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) SetResumePath(ctx context.Context, applicationID int64, filePath string) error {
	result, err := s.db.ExecContext(ctx, `UPDATE resumes SET file_path=? WHERE id=(SELECT resume_id FROM applications WHERE id=?)`, filePath, applicationID)
	if err != nil {
		return err
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if changed == 0 {
		return errors.New("投递记录不存在")
	}
	return nil
}

func (s *Store) ResumePath(ctx context.Context, applicationID int64) (string, error) {
	var filePath string
	err := s.db.QueryRowContext(ctx, `SELECT r.file_path FROM resumes r JOIN applications a ON a.resume_id=r.id WHERE a.id=?`, applicationID).Scan(&filePath)
	if errors.Is(err, sql.ErrNoRows) {
		return "", errors.New("投递记录不存在")
	}
	if err != nil {
		return "", err
	}
	return s.resolveStoredPath(filePath), nil
}

func (s *Store) resolveStoredPath(stored string) string {
	stored = strings.TrimSpace(stored)
	if stored == "" || filepath.IsAbs(stored) {
		return stored
	}
	parts := strings.Split(filepath.ToSlash(stored), "/")
	if len(parts) > 1 && strings.EqualFold(parts[0], "data") {
		return filepath.Join(append([]string{s.dataDir}, parts[1:]...)...)
	}
	return filepath.Join(s.dataDir, filepath.FromSlash(stored))
}

func (s *Store) Backup(ctx context.Context, destination string) error {
	if strings.TrimSpace(destination) == "" {
		return errors.New("备份路径不能为空")
	}
	_, err := s.db.ExecContext(ctx, "VACUUM INTO ?", destination)
	if err != nil {
		return fmt.Errorf("创建数据库备份: %w", err)
	}
	return nil
}

func (s *Store) BusinessDataEmpty(ctx context.Context) (bool, error) {
	tables := []string{"resumes", "applications", "materials", "profile", "job_targets", "application_attachments", "job_tasks", "interviews"}
	total := 0
	for _, table := range tables {
		var count int
		if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM "+table).Scan(&count); err != nil {
			return false, err
		}
		total += count
	}
	return total == 0, nil
}

func (s *Store) ImportV3Snapshot(ctx context.Context, snapshot string) error {
	if demo, err := s.HasDemo(ctx); err != nil {
		return err
	} else if demo {
		if err := s.ClearDemo(ctx); err != nil {
			return err
		}
	}
	empty, err := s.BusinessDataEmpty(ctx)
	if err != nil {
		return err
	}
	if !empty {
		return errors.New("v4 已有业务数据，不能一键导入以免混合")
	}
	conn, err := s.db.Conn(ctx)
	if err != nil {
		return err
	}
	defer conn.Close()
	if _, err := conn.ExecContext(ctx, "ATTACH DATABASE ? AS legacy", snapshot); err != nil {
		return err
	}
	defer conn.ExecContext(context.Background(), "DETACH DATABASE legacy")
	tx, err := conn.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, table := range []string{"resumes", "materials", "profile", "job_targets", "applications", "application_attachments", "job_tasks", "interviews"} {
		if _, err := tx.ExecContext(ctx, "INSERT INTO main."+table+" SELECT * FROM legacy."+table); err != nil {
			return fmt.Errorf("导入表 %s: %w", table, err)
		}
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	_, err = conn.ExecContext(ctx, repairLegacyTargetsSQL)
	return err
}

func ParseID(raw string) (int64, error) {
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id < 1 {
		return 0, errors.New("无效的投递编号")
	}
	return id, nil
}

func (s *Store) Dashboard(ctx context.Context) (Dashboard, error) {
	items, err := s.ListApplications(ctx)
	if err != nil {
		return Dashboard{}, err
	}
	d := Dashboard{Total: len(items), StageCounts: map[string]int{}}
	terminal := map[string]bool{"终止": true, "已终止": true, "未通过": true, "主动放弃": true, "流程结束": true}
	for _, item := range items {
		d.StageCounts[item.CurrentStatus]++
		if !terminal[item.CurrentStatus] {
			d.Active++
		}
		if strings.Contains(item.CurrentStatus, "面") {
			d.Interview++
		}
		if item.CurrentStatus == "Offer" {
			d.Offers++
		}
	}
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM job_tasks WHERE state='open'").Scan(&d.OpenTasks); err != nil {
		return Dashboard{}, err
	}
	d.Demo, err = s.HasDemo(ctx)
	if err != nil {
		return Dashboard{}, err
	}
	return d, nil
}

func parseHistory(raw string) []StatusEvent {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return []StatusEvent{}
	}
	var events []StatusEvent
	if json.Valid([]byte(raw)) && json.Unmarshal([]byte(raw), &events) == nil {
		return events
	}
	for _, line := range strings.Split(raw, "\n") {
		parts := legacyHistoryLine.FindStringSubmatch(strings.TrimSpace(line))
		if len(parts) == 4 {
			events = append(events, StatusEvent{From: strings.TrimSpace(parts[2]), To: strings.TrimSpace(parts[3]), Time: strings.TrimSpace(parts[1]), Note: "v3 历史记录"})
		}
	}
	return events
}
