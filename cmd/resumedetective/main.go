package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Suryxin-xx/ResumeDetective/internal/ai"
	"github.com/Suryxin-xx/ResumeDetective/internal/autostart"
	"github.com/Suryxin-xx/ResumeDetective/internal/brand"
	"github.com/Suryxin-xx/ResumeDetective/internal/config"
	"github.com/Suryxin-xx/ResumeDetective/internal/excelmirror"
	"github.com/Suryxin-xx/ResumeDetective/internal/httpapi"
	"github.com/Suryxin-xx/ResumeDetective/internal/migrate"
	"github.com/Suryxin-xx/ResumeDetective/internal/settings"
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	"github.com/Suryxin-xx/ResumeDetective/internal/tray"
	"github.com/Suryxin-xx/ResumeDetective/internal/update"
	"github.com/Suryxin-xx/ResumeDetective/internal/webui"
)

var version = "4.1.0-dev"

func main() {
	var dataDir string
	var portOverride int
	var noBrowser bool
	var noTray bool
	var applyUpdate string
	var updateTarget string
	var updateSHA256 string
	flag.StringVar(&dataDir, "data-dir", "", "数据目录；默认使用 EXE 旁的 data 文件夹")
	flag.IntVar(&portOverride, "port", 0, "临时覆盖本机网页端口")
	flag.BoolVar(&noBrowser, "no-browser", false, "启动后不自动打开浏览器")
	flag.BoolVar(&noTray, "no-tray", false, "不显示 Windows 托盘图标（仅调试）")
	flag.StringVar(&applyUpdate, "apply-update", "", "内部参数：应用已验证的更新包")
	flag.StringVar(&updateTarget, "update-target", "", "内部参数：需要替换的程序")
	flag.StringVar(&updateSHA256, "update-sha256", "", "内部参数：更新包 SHA-256")
	flag.Parse()
	if applyUpdate != "" {
		if err := update.ApplyPackage(applyUpdate, updateTarget, updateSHA256); err != nil {
			_ = os.WriteFile(filepath.Join(filepath.Dir(applyUpdate), "update-error.log"), []byte(err.Error()+"\n"), 0o600)
		}
		return
	}

	bootstrapLogger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))
	paths, err := config.Resolve(dataDir)
	if err != nil {
		bootstrapLogger.Error("准备便携数据目录失败", "error", err)
		return
	}
	manager, err := settings.Open(paths.ConfigFile, paths.EnvFile)
	if err != nil {
		bootstrapLogger.Error("加载设置失败", "error", err)
		return
	}
	cfg := manager.Get()
	port := cfg.Port
	if portOverride != 0 {
		port = portOverride
	}
	if port < 1024 || port > 65535 {
		bootstrapLogger.Error("端口必须在 1024 到 65535 之间")
		return
	}

	logger := bootstrapLogger
	if logFile, err := os.OpenFile(filepath.Join(paths.DataDir, "resumedetective.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600); err == nil {
		defer logFile.Close()
		logger = slog.New(slog.NewTextHandler(logFile, &slog.HandlerOptions{Level: slog.LevelInfo}))
	}
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	url := "http://" + addr
	if existingInstance(url) {
		if !noBrowser {
			_ = openBrowser(url)
		}
		return
	}

	st, err := store.Open(paths.Database)
	if err != nil {
		logger.Error("打开数据库失败", "error", err)
		return
	}
	defer st.Close()
	if err := excelmirror.Sync(context.Background(), st, paths.Workbook); err != nil {
		logger.Warn("启动时同步 Excel 镜像失败", "path", paths.Workbook, "error", err)
	}
	files, err := webui.Files()
	if err != nil {
		logger.Error("加载网页资源失败", "error", err)
		return
	}
	listener, err := net.Listen("tcp4", addr)
	if err != nil {
		logger.Error("端口无法使用", "address", addr, "error", err)
		return
	}

	stopRequested := make(chan struct{})
	var stopOnce sync.Once
	finalAction := "quit"
	requestAction := func(action string) {
		stopOnce.Do(func() {
			finalAction = action
			close(stopRequested)
		})
	}
	v3Dir := migrate.Discover("")
	aiService := ai.New(st, manager, paths.DataDir)
	updateService := update.New(version, paths.UpdatesDir)
	autostartService := autostart.New("ResumeDetective")
	httpapi.Version = version
	handler := httpapi.NewWithOptions(st, files, paths, v3Dir, func() { requestAction("quit") }, logger, httpapi.Options{
		Settings:  manager,
		AI:        aiService,
		Updater:   updateService,
		AutoStart: autostartService,
		Restart:   func() { requestAction("restart") },
	})
	server := httpapi.NewHTTPServer(addr, handler)
	logger.Info("ResumeDetective 已启动", "version", version, "url", url, "data", paths.DataDir)

	serverContext, cancelServerContext := context.WithCancel(context.Background())
	defer cancelServerContext()
	go runAutoBackup(serverContext, st, paths, manager, logger)
	go func() {
		if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
			logger.Error("服务异常停止", "error", err)
			requestAction("quit")
		}
	}()

	if cfg.OpenBrowserOnStart && !noBrowser {
		go func() {
			time.Sleep(250 * time.Millisecond)
			if err := openBrowser(url); err != nil {
				logger.Warn("未能自动打开浏览器", "error", err)
			}
		}()
	}
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	go func() {
		select {
		case <-signals:
			requestAction("quit")
		case <-stopRequested:
		}
	}()

	if runtime.GOOS == "windows" && !noTray {
		go func() {
			<-stopRequested
			tray.Quit()
		}()
		tray.Run(brand.IconICO, cfg.WorkspaceName+"正在本机运行", url, tray.Actions{
			Open:         func() { _ = openBrowser(url) },
			Restart:      func() { requestAction("restart") },
			CheckUpdates: func() { _ = openBrowser(url + "/#settings") },
			Quit:         func() { requestAction("quit") },
		})
	} else {
		<-stopRequested
	}

	cancelServerContext()
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	_ = server.Shutdown(ctx)
	cancel()
	if finalAction == "restart" {
		if err := relaunch(); err != nil {
			logger.Error("重启失败", "error", err)
		}
	}
}

func existingInstance(baseURL string) bool {
	client := http.Client{Timeout: 800 * time.Millisecond}
	response, err := client.Get(baseURL + "/api/health")
	if err != nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode == http.StatusOK
}

func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}

func relaunch() error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	command := exec.Command(executable, os.Args[1:]...)
	command.Dir = filepath.Dir(executable)
	return command.Start()
}

func runAutoBackup(ctx context.Context, st *store.Store, paths config.Paths, manager *settings.Manager, logger *slog.Logger) {
	check := func() {
		cfg := manager.Get()
		latest := latestBackupTime(paths.BackupsDir)
		if !settings.ShouldRunBackup(latest, cfg, time.Now()) {
			return
		}
		name := "automatic-" + time.Now().Format("20060102-150405") + ".db"
		if err := st.Backup(ctx, filepath.Join(paths.BackupsDir, name)); err != nil {
			if ctx.Err() == nil {
				logger.Warn("自动备份失败", "error", err)
			}
			return
		}
		if err := pruneAutomaticBackups(paths.BackupsDir, cfg.BackupRetention); err != nil {
			logger.Warn("清理过期自动备份失败", "error", err)
		}
		logger.Info("自动备份完成", "file", name)
	}
	check()
	ticker := time.NewTicker(15 * time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			check()
		case <-ctx.Done():
			return
		}
	}
}

func pruneAutomaticBackups(dir string, keep int) error {
	if keep < 1 {
		return nil
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}
	type backupFile struct {
		path    string
		modTime time.Time
	}
	backups := make([]backupFile, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasPrefix(entry.Name(), "automatic-") || filepath.Ext(entry.Name()) != ".db" {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		backups = append(backups, backupFile{path: filepath.Join(dir, entry.Name()), modTime: info.ModTime()})
	}
	sort.Slice(backups, func(i, j int) bool { return backups[i].modTime.After(backups[j].modTime) })
	if len(backups) <= keep {
		return nil
	}
	for _, backup := range backups[keep:] {
		if err := os.Remove(backup.path); err != nil {
			return err
		}
	}
	return nil
}

func latestBackupTime(dir string) time.Time {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return time.Time{}
	}
	var latest time.Time
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".db" {
			continue
		}
		if info, err := entry.Info(); err == nil && info.ModTime().After(latest) {
			latest = info.ModTime()
		}
	}
	return latest
}
