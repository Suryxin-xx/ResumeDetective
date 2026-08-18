package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"net"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/ai"
	"github.com/Suryxin-xx/ResumeDetective/internal/autostart"
	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/excelmirror"
	"github.com/Suryxin-xx/ResumeDetective/internal/migrate"
	"github.com/Suryxin-xx/ResumeDetective/internal/settings"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	"github.com/Suryxin-xx/ResumeDetective/internal/update"
)

type Server struct {
	store         *store.Store
	web           fs.FS
	log           *slog.Logger
	resumesDir    string
	backupsDir    string
	paths         config.Paths
	v3Dir         string
	shutdown      func()
	restart       func()
	settings      *settings.Manager
	ai            *ai.Service
	updater       *update.Service
	autostart     autostart.Controller
	pickDirectory func(context.Context) (string, error)
}

var Version = "4.2.0-dev"

type Options struct {
	Settings      *settings.Manager
	AI            *ai.Service
	Restart       func()
	Updater       *update.Service
	AutoStart     autostart.Controller
	PickDirectory func(context.Context) (string, error)
}

func New(st *store.Store, web fs.FS, paths config.Paths, v3Dir string, shutdown func(), logger *slog.Logger) http.Handler {
	return NewWithOptions(st, web, paths, v3Dir, shutdown, logger, Options{})
}

func NewWithOptions(st *store.Store, web fs.FS, paths config.Paths, v3Dir string, shutdown func(), logger *slog.Logger, options Options) http.Handler {
	s := &Server{store: st, web: web, log: logger, resumesDir: paths.ResumesDir, backupsDir: paths.BackupsDir, paths: paths, v3Dir: v3Dir, shutdown: shutdown, restart: options.Restart, settings: options.Settings, ai: options.AI, updater: options.Updater, autostart: options.AutoStart, pickDirectory: options.PickDirectory}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", s.health)
	mux.HandleFunc("GET /api/dashboard", s.dashboard)
	mux.HandleFunc("GET /api/applications", s.listApplications)
	mux.HandleFunc("POST /api/applications", s.createApplication)
	mux.HandleFunc("PATCH /api/applications/{id}", s.updateApplication)
	mux.HandleFunc("DELETE /api/applications/{id}", s.deleteApplication)
	mux.HandleFunc("POST /api/applications/{id}/resume", s.uploadResume)
	mux.HandleFunc("POST /api/applications/{id}/resume/rename", s.renameResume)
	mux.HandleFunc("GET /resume/{id}", s.viewResume)
	mux.HandleFunc("POST /api/backups", s.createBackup)
	mux.HandleFunc("DELETE /api/demo", s.clearDemo)
	mux.HandleFunc("GET /api/migration/status", s.migrationStatus)
	mux.HandleFunc("POST /api/migration/inspect", s.inspectV3)
	mux.HandleFunc("POST /api/migration/select", s.selectV3Directory)
	mux.HandleFunc("POST /api/migration/import", s.importV3)
	mux.HandleFunc("POST /api/system/quit", s.quit)
	mux.HandleFunc("POST /api/system/restart", s.restartApp)
	mux.HandleFunc("GET /api/system/info", s.systemInfo)
	mux.HandleFunc("GET /api/settings", s.getSettings)
	mux.HandleFunc("PUT /api/settings", s.saveSettings)
	mux.HandleFunc("POST /api/ai/test", s.testAI)
	mux.HandleFunc("GET /api/ai/balance", s.aiBalance)
	mux.HandleFunc("POST /api/ai/analyze", s.analyzeAI)
	mux.HandleFunc("GET /api/profile", s.getProfile)
	mux.HandleFunc("PUT /api/profile", s.saveProfile)
	mux.HandleFunc("GET /api/materials", s.listMaterials)
	mux.HandleFunc("POST /api/materials", s.createMaterial)
	mux.HandleFunc("PATCH /api/materials/{id}", s.updateMaterial)
	mux.HandleFunc("DELETE /api/materials/{id}", s.deleteMaterial)
	mux.HandleFunc("GET /api/updates/check", s.checkUpdate)
	mux.HandleFunc("POST /api/updates/download", s.downloadUpdate)
	mux.HandleFunc("POST /api/updates/install", s.installUpdate)
	mux.HandleFunc("GET /api/targets", s.listTargets)
	mux.HandleFunc("POST /api/targets", s.createTarget)
	mux.HandleFunc("PATCH /api/targets/{id}", s.updateTarget)
	mux.HandleFunc("DELETE /api/targets/{id}", s.deleteTarget)
	mux.HandleFunc("POST /api/targets/{id}/convert", s.convertTarget)
	mux.HandleFunc("GET /api/tasks", s.listTasks)
	mux.HandleFunc("POST /api/tasks", s.createTask)
	mux.HandleFunc("PATCH /api/tasks/{id}/state", s.setTaskState)
	mux.HandleFunc("DELETE /api/tasks/{id}", s.deleteTask)
	mux.HandleFunc("GET /api/interviews", s.listInterviews)
	mux.HandleFunc("POST /api/interviews", s.createInterview)
	mux.HandleFunc("PATCH /api/interviews/{id}", s.updateInterview)
	mux.HandleFunc("DELETE /api/interviews/{id}", s.deleteInterview)
	mux.HandleFunc("GET /api/offers", s.listOffers)
	mux.HandleFunc("PUT /api/offers", s.upsertOffer)
	mux.HandleFunc("DELETE /api/offers/{id}", s.deleteOffer)
	mux.HandleFunc("/", s.static)
	return s.securityHeaders(s.localOnly(mux))
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "version": Version})
}

func (s *Server) dashboard(w http.ResponseWriter, r *http.Request) {
	item, err := s.store.Dashboard(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) listApplications(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListApplications(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func (s *Server) createApplication(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 2<<20)
	var in store.CreateApplicationInput
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "提交内容格式不正确")
		return
	}
	id, err := s.store.CreateApplication(r.Context(), in)
	if err != nil {
		if strings.Contains(err.Error(), "不能为空") {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		s.internalError(w, r, err)
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusCreated, map[string]int64{"id": id})
}

func (s *Server) updateApplication(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 2<<20)
	var in store.UpdateApplicationInput
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "提交内容格式不正确")
		return
	}
	if err := s.store.UpdateApplication(r.Context(), id, in); err != nil {
		if strings.Contains(err.Error(), "无效") || strings.Contains(err.Error(), "不存在") {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		s.internalError(w, r, err)
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) deleteApplication(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.store.DeleteApplication(r.Context(), id); err != nil {
		if strings.Contains(err.Error(), "无效") || strings.Contains(err.Error(), "不存在") {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		s.internalError(w, r, err)
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) uploadResume(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 25<<20)
	file, header, err := r.FormFile("resume")
	if err != nil {
		writeError(w, http.StatusBadRequest, "请选择不超过 25 MB 的简历文件")
		return
	}
	defer file.Close()
	ext := strings.ToLower(filepath.Ext(header.Filename))
	allowed := map[string]bool{".pdf": true, ".doc": true, ".docx": true}
	if !allowed[ext] {
		writeError(w, http.StatusBadRequest, "简历仅支持 PDF、DOC 或 DOCX")
		return
	}
	app, err := s.store.GetApplication(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	baseName := sanitizeResumeName(strings.TrimSuffix(filepath.Base(header.Filename), filepath.Ext(header.Filename)))
	if s.settings != nil {
		cfg := s.settings.Get()
		if cfg.AutoRenameResumes {
			baseName = renderResumeName(cfg.ResumeNameTemplate, app, time.Now())
		}
	}
	if baseName == "" {
		baseName = renderResumeName(settings.DefaultResumeNameTemplate, app, time.Now())
	}
	tempName, err := availableResumePath(s.resumesDir, baseName, ext, "")
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	temp, err := os.OpenFile(tempName, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	keep := false
	defer func() {
		_ = temp.Close()
		if !keep {
			_ = os.Remove(tempName)
		}
	}()
	if _, err := io.Copy(temp, io.LimitReader(file, 25<<20)); err != nil {
		s.internalError(w, r, err)
		return
	}
	if err := temp.Sync(); err != nil {
		s.internalError(w, r, err)
		return
	}
	if err := temp.Close(); err != nil {
		s.internalError(w, r, err)
		return
	}
	if err := s.store.SetResumePath(r.Context(), id, tempName); err != nil {
		if strings.Contains(err.Error(), "不存在") {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		s.internalError(w, r, err)
		return
	}
	keep = true
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusCreated, map[string]bool{"ok": true})
}

func (s *Server) renameResume(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	app, err := s.store.GetApplication(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	current, err := s.store.ResumePath(r.Context(), id)
	if err != nil || strings.TrimSpace(current) == "" {
		writeError(w, http.StatusBadRequest, "该投递尚未绑定简历")
		return
	}
	if !pathInsideDirectory(s.resumesDir, current) {
		writeError(w, http.StatusBadRequest, "为保护外部文件，只能重命名 data/resumes 内的简历")
		return
	}
	if info, statErr := os.Stat(current); statErr != nil || !info.Mode().IsRegular() {
		writeError(w, http.StatusBadRequest, "简历文件不存在或不可访问")
		return
	}
	template := settings.DefaultResumeNameTemplate
	if s.settings != nil {
		template = s.settings.Get().ResumeNameTemplate
	}
	next, err := availableResumePath(s.resumesDir, renderResumeName(template, app, time.Now()), strings.ToLower(filepath.Ext(current)), current)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	if filepath.Clean(next) == filepath.Clean(current) {
		writeJSON(w, http.StatusOK, map[string]any{"renamed": false, "fileName": filepath.Base(current)})
		return
	}
	if err := os.Rename(current, next); err != nil {
		s.internalError(w, r, err)
		return
	}
	if err := s.store.ReplaceResumePath(r.Context(), id, next); err != nil {
		_ = os.Rename(next, current)
		s.internalError(w, r, err)
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"renamed": true, "fileName": filepath.Base(next)})
}

func (s *Server) viewResume(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	filePath, err := s.store.ResumePath(r.Context(), id)
	if err != nil || strings.TrimSpace(filePath) == "" {
		http.NotFound(w, r)
		return
	}
	file, err := os.Open(filePath)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		http.NotFound(w, r)
		return
	}
	name := filepath.Base(filePath)
	w.Header().Set("Content-Disposition", fmt.Sprintf("inline; filename=%q", strings.ReplaceAll(name, `"`, "")))
	http.ServeContent(w, r, name, info.ModTime(), file)
}

func (s *Server) createBackup(w http.ResponseWriter, r *http.Request) {
	name := "resume-detective-" + time.Now().Format("20060102-150405") + ".db"
	destination := filepath.Join(s.backupsDir, name)
	if err := s.store.Backup(r.Context(), destination); err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"fileName": name})
}

func (s *Server) clearDemo(w http.ResponseWriter, r *http.Request) {
	if err := s.store.ClearDemo(r.Context()); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) migrationStatus(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, migrate.Inspect(s.v3Dir))
}

func (s *Server) inspectV3(w http.ResponseWriter, r *http.Request) {
	var in struct {
		SourceDir string `json:"sourceDir"`
	}
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	writeJSON(w, http.StatusOK, migrate.Inspect(in.SourceDir))
}

func (s *Server) selectV3Directory(w http.ResponseWriter, r *http.Request) {
	if s.pickDirectory == nil {
		writeError(w, http.StatusServiceUnavailable, "当前运行模式不支持选择文件夹，请手动填写路径")
		return
	}
	directory, err := s.pickDirectory(r.Context())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if strings.TrimSpace(directory) == "" {
		writeJSON(w, http.StatusOK, map[string]bool{"canceled": true})
		return
	}
	writeJSON(w, http.StatusOK, migrate.Inspect(directory))
}

func (s *Server) importV3(w http.ResponseWriter, r *http.Request) {
	var in struct {
		SourceDir string `json:"sourceDir"`
	}
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	sourceDir := strings.TrimSpace(in.SourceDir)
	if sourceDir == "" {
		sourceDir = s.v3Dir
	}
	report, err := migrate.ImportIntoStore(r.Context(), s.store, s.paths, sourceDir)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusCreated, report)
}

func (s *Server) quit(w http.ResponseWriter, _ *http.Request) {
	if s.shutdown == nil {
		writeError(w, http.StatusServiceUnavailable, "当前运行模式不支持网页退出")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
	go func() {
		time.Sleep(150 * time.Millisecond)
		s.shutdown()
	}()
}

func (s *Server) restartApp(w http.ResponseWriter, _ *http.Request) {
	if s.restart == nil {
		writeError(w, http.StatusServiceUnavailable, "当前运行模式不支持重启")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
	go func() {
		time.Sleep(150 * time.Millisecond)
		s.restart()
	}()
}

func (s *Server) systemInfo(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"version": Version, "dataDir": s.paths.DataDir,
		"developer": map[string]string{
			"name": "Suryxin-xx", "email": "Finlandxxu@outlook.com", "repository": "https://github.com/Suryxin-xx/ResumeDetective",
		},
	})
}

func (s *Server) getSettings(w http.ResponseWriter, _ *http.Request) {
	if s.settings == nil {
		writeError(w, http.StatusServiceUnavailable, "设置服务未启用")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"config": s.settings.Get(), "apiKeyConfigured": s.settings.HasAPIKey(), "dataDir": s.paths.DataDir})
}

func (s *Server) saveSettings(w http.ResponseWriter, r *http.Request) {
	if s.settings == nil {
		writeError(w, http.StatusServiceUnavailable, "设置服务未启用")
		return
	}
	var in struct {
		Config       settings.Config `json:"config"`
		APIKey       string          `json:"apiKey"`
		DeleteAPIKey bool            `json:"deleteApiKey"`
	}
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	oldConfig := s.settings.Get()
	if s.autostart != nil && oldConfig.StartAtLogin != in.Config.StartAtLogin {
		if err := s.autostart.Set(in.Config.StartAtLogin); err != nil {
			writeError(w, http.StatusBadRequest, "设置 Windows 登录自启失败: "+err.Error())
			return
		}
	}
	if err := s.settings.Save(in.Config); err != nil {
		if s.autostart != nil && oldConfig.StartAtLogin != in.Config.StartAtLogin {
			_ = s.autostart.Set(oldConfig.StartAtLogin)
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if in.DeleteAPIKey {
		if err := s.settings.DeleteAPIKey(); err != nil {
			writeError(w, http.StatusInternalServerError, "删除 API Key 失败")
			return
		}
	} else if strings.TrimSpace(in.APIKey) != "" {
		if err := s.settings.SaveAPIKey(in.APIKey); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "restartRequired": true, "apiKeyConfigured": s.settings.HasAPIKey()})
}

func (s *Server) getProfile(w http.ResponseWriter, r *http.Request) {
	item, err := s.store.GetProfile(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}
func (s *Server) saveProfile(w http.ResponseWriter, r *http.Request) {
	var in store.Profile
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	if err := s.store.SaveProfile(r.Context(), in); err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) listMaterials(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListMaterials(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) createMaterial(w http.ResponseWriter, r *http.Request) {
	var in store.MaterialInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	id, err := s.store.CreateMaterial(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]int64{"id": id})
}
func (s *Server) updateMaterial(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "无效的经历编号")
		return
	}
	var in store.MaterialInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	if err := s.store.UpdateMaterial(r.Context(), id, in); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) deleteMaterial(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "无效的经历编号")
		return
	}
	if err := s.store.DeleteMaterial(r.Context(), id); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) testAI(w http.ResponseWriter, r *http.Request) {
	if s.ai == nil {
		writeError(w, http.StatusServiceUnavailable, "AI 服务未启用")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	result, err := s.ai.Test(ctx)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) aiBalance(w http.ResponseWriter, r *http.Request) {
	if s.ai == nil {
		writeError(w, http.StatusServiceUnavailable, "AI 服务未启用")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	result, err := s.ai.Balance(ctx)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) analyzeAI(w http.ResponseWriter, r *http.Request) {
	if s.ai == nil {
		writeError(w, http.StatusServiceUnavailable, "AI 服务未启用")
		return
	}
	var in ai.Request
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()
	result, err := s.ai.Analyze(ctx, in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) checkUpdate(w http.ResponseWriter, r *http.Request) {
	if s.updater == nil {
		writeError(w, http.StatusServiceUnavailable, "更新服务未启用")
		return
	}
	repository := update.ResumeDetectiveRepo
	if r.URL.Query().Get("component") == "reasonix" {
		repository = update.ReasonixRepo
	}
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	info, err := s.updater.Check(ctx, repository)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, info)
}

func (s *Server) downloadUpdate(w http.ResponseWriter, r *http.Request) {
	if s.updater == nil {
		writeError(w, http.StatusServiceUnavailable, "更新服务未启用")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	download, err := s.updater.Download(ctx)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, download)
}

func (s *Server) installUpdate(w http.ResponseWriter, r *http.Request) {
	if s.updater == nil || s.shutdown == nil {
		writeError(w, http.StatusServiceUnavailable, "当前运行模式不支持自动安装")
		return
	}
	var download update.Download
	if err := decodeJSON(w, r, &download); err != nil {
		return
	}
	if err := s.updater.StartInstall(download); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]bool{"ok": true})
	go func() {
		time.Sleep(250 * time.Millisecond)
		s.shutdown()
	}()
}

func (s *Server) listTargets(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListJobTargets(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func (s *Server) createTarget(w http.ResponseWriter, r *http.Request) {
	var in store.JobTargetInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	id, err := s.store.CreateJobTarget(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]int64{"id": id})
}

func (s *Server) updateTarget(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "无效的意向编号")
		return
	}
	var in store.JobTargetInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	if err := s.store.UpdateJobTarget(r.Context(), id, in); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) deleteTarget(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "无效的意向编号")
		return
	}
	if err := s.store.DeleteJobTarget(r.Context(), id); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) convertTarget(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "无效的意向编号")
		return
	}
	var in store.ConvertTargetInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	applicationID, err := s.store.ConvertJobTarget(r.Context(), id, in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusCreated, map[string]int64{"applicationId": applicationID})
}

func (s *Server) listTasks(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListTasks(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) createTask(w http.ResponseWriter, r *http.Request) {
	var in store.CreateTaskInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	id, err := s.store.CreateTask(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]int64{"id": id})
}
func (s *Server) setTaskState(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	var in struct {
		State string `json:"state"`
	}
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	if err := s.store.SetTaskState(r.Context(), id, in.State); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) deleteTask(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.store.DeleteTask(r.Context(), id); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) listInterviews(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListInterviews(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) createInterview(w http.ResponseWriter, r *http.Request) {
	var in store.CreateInterviewInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	id, err := s.store.CreateInterview(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusCreated, map[string]int64{"id": id})
}
func (s *Server) updateInterview(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	var in store.CreateInterviewInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	if err := s.store.UpdateInterview(r.Context(), id, in); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
func (s *Server) deleteInterview(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.store.DeleteInterview(r.Context(), id); err != nil {
		writeError(w, http.StatusBadRequest, "面试记录不存在")
		return
	}
	s.syncApplicationWorkbook(r.Context())
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) listOffers(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListOffers(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}

func (s *Server) upsertOffer(w http.ResponseWriter, r *http.Request) {
	var in store.UpsertOfferInput
	if err := decodeJSON(w, r, &in); err != nil {
		return
	}
	id, err := s.store.UpsertOffer(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]int64{"id": id})
}

func (s *Server) deleteOffer(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.store.DeleteOffer(r.Context(), id); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (s *Server) syncApplicationWorkbook(ctx context.Context) {
	if err := excelmirror.Sync(ctx, s.store, s.paths.Workbook); err != nil {
		s.log.Warn("同步 Excel 镜像失败", "path", s.paths.Workbook, "error", err)
	}
}

func decodeJSON(w http.ResponseWriter, r *http.Request, value any) error {
	r.Body = http.MaxBytesReader(w, r.Body, 2<<20)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		writeError(w, http.StatusBadRequest, "提交内容格式不正确")
		return err
	}
	return nil
}

func (s *Server) static(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		writeError(w, http.StatusMethodNotAllowed, "不支持此请求")
		return
	}
	name := strings.TrimPrefix(path.Clean(r.URL.Path), "/")
	if name == "." || name == "" {
		name = "index.html"
	}
	if _, err := fs.Stat(s.web, name); err != nil {
		if !errors.Is(err, fs.ErrNotExist) {
			s.internalError(w, r, err)
			return
		}
		name = "index.html"
	}
	data, err := fs.ReadFile(s.web, name)
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	switch path.Ext(name) {
	case ".html":
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
	case ".css":
		w.Header().Set("Content-Type", "text/css; charset=utf-8")
	case ".js":
		w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
	}
	w.Header().Set("Cache-Control", "no-cache")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

func (s *Server) localOnly(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := r.Host
		if parsed, _, err := net.SplitHostPort(r.Host); err == nil {
			host = parsed
		}
		if host != "127.0.0.1" && host != "localhost" && host != "[::1]" && host != "::1" {
			writeError(w, http.StatusForbidden, "只允许从本机访问")
			return
		}
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			origin := r.Header.Get("Origin")
			if origin != "" && origin != "http://"+r.Host && origin != "https://"+r.Host {
				writeError(w, http.StatusForbidden, "拒绝跨站修改本地数据")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(w, r)
	})
}

func (s *Server) internalError(w http.ResponseWriter, r *http.Request, err error) {
	s.log.Error("request failed", "method", r.Method, "path", r.URL.Path, "error", err)
	writeError(w, http.StatusInternalServerError, "本机服务处理失败，请查看日志")
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func NewHTTPServer(addr string, handler http.Handler) *http.Server {
	return &http.Server{Addr: addr, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 90 * time.Second}
}
