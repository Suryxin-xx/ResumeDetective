package update

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

const (
	ResumeDetectiveRepo = "Suryxin-xx/ResumeDetective"
	ReasonixRepo        = "esengine/DeepSeek-Reasonix"
	maxReleaseResponse  = int64(2 << 20)
	maxUpdateBytes      = int64(300 << 20)
)

var semverPattern = regexp.MustCompile(`^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$`)
var releaseTagPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$`)

type Asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
	Size               int64  `json:"size"`
	Digest             string `json:"digest"`
}

type releasePayload struct {
	TagName    string  `json:"tag_name"`
	Name       string  `json:"name"`
	Body       string  `json:"body"`
	HTMLURL    string  `json:"html_url"`
	Draft      bool    `json:"draft"`
	Prerelease bool    `json:"prerelease"`
	Assets     []Asset `json:"assets"`
}

type Info struct {
	Repository    string `json:"repository"`
	Current       string `json:"current"`
	Latest        string `json:"latest"`
	Name          string `json:"name"`
	Notes         string `json:"notes"`
	ReleaseURL    string `json:"releaseUrl"`
	Available     bool   `json:"available"`
	CanAutoUpdate bool   `json:"canAutoUpdate"`
	AssetName     string `json:"assetName,omitempty"`
	AssetSize     int64  `json:"assetSize,omitempty"`
	Reason        string `json:"reason,omitempty"`
}

type Download struct {
	Version string `json:"version"`
	Path    string `json:"path"`
	SHA256  string `json:"sha256"`
	Size    int64  `json:"size"`
}

type Service struct {
	CurrentVersion string
	UpdatesDir     string
	APIBase        string
	WebBase        string
	Client         *http.Client
}

func New(currentVersion, updatesDir string) *Service {
	client := &http.Client{Timeout: 45 * time.Second}
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) > 8 || req.URL == nil || req.URL.Scheme != "https" || !trustedHost(req.URL.Hostname()) {
			return errors.New("更新下载重定向到了不受信任的地址")
		}
		return nil
	}
	return &Service{CurrentVersion: currentVersion, UpdatesDir: updatesDir, APIBase: "https://api.github.com", WebBase: "https://github.com", Client: client}
}

func (s *Service) Check(ctx context.Context, repository string) (Info, error) {
	if repository != ResumeDetectiveRepo && repository != ReasonixRepo {
		return Info{}, errors.New("不受信任的更新仓库")
	}
	endpoint := strings.TrimRight(s.APIBase, "/") + "/repos/" + repository + "/releases/latest"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return Info{}, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2026-03-10")
	req.Header.Set("User-Agent", "ResumeDetective-Updater/4")
	resp, err := s.Client.Do(req)
	var release releasePayload
	fallback := false
	if err != nil {
		release, err = s.releasePageFallback(ctx, repository)
		fallback = true
		if err != nil {
			return Info{}, err
		}
	} else if resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusTooManyRequests {
		defer resp.Body.Close()
		release, err = s.releasePageFallback(ctx, repository)
		fallback = true
		if err != nil {
			return Info{}, err
		}
	} else {
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return Info{}, fmt.Errorf("GitHub Release 返回 %d", resp.StatusCode)
		}
		if err := json.NewDecoder(io.LimitReader(resp.Body, maxReleaseResponse)).Decode(&release); err != nil {
			return Info{}, errors.New("GitHub Release 返回格式不正确")
		}
	}
	if release.Draft {
		return Info{}, errors.New("最新 Release 仍是草稿")
	}
	info := Info{Repository: repository, Current: s.CurrentVersion, Latest: release.TagName, Name: release.Name, Notes: release.Body, ReleaseURL: release.HTMLURL}
	if repository == ReasonixRepo {
		info.Available = true
		info.Reason = "Reasonix 使用独立版本线，请在官方 Release 确认后更新"
		return info, nil
	}
	comparison, ok := compareVersions(s.CurrentVersion, release.TagName)
	if !ok {
		info.Reason = "开发版不参与自动版本比较"
		return info, nil
	}
	info.Available = comparison < 0
	if fallback {
		info.Reason = "GitHub API 暂不可用；已通过官方发布页确认版本，自动下载安装稍后可重试"
		return info, nil
	}
	asset := selectWindowsAsset(release.Assets)
	if asset == nil {
		info.Reason = "Release 中没有 Windows x64 ZIP"
		return info, nil
	}
	info.AssetName, info.AssetSize = asset.Name, asset.Size
	digest, ok := normalizedDigest(asset.Digest)
	if !ok {
		info.Reason = "Release 资产缺少 SHA-256 digest，只能手动更新"
		return info, nil
	}
	_ = digest
	info.CanAutoUpdate = info.Available && asset.Size > 0 && asset.Size <= maxUpdateBytes
	return info, nil
}

func (s *Service) releasePageFallback(ctx context.Context, repository string) (releasePayload, error) {
	endpoint := strings.TrimRight(s.WebBase, "/") + "/" + repository + "/releases/latest"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return releasePayload{}, err
	}
	req.Header.Set("User-Agent", "ResumeDetective-Updater/4")
	response, err := s.Client.Do(req)
	if err != nil {
		return releasePayload{}, fmt.Errorf("GitHub API 已限流，发布页检查也失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 400 || response.Request == nil || response.Request.URL == nil {
		return releasePayload{}, errors.New("GitHub API 已限流，暂时无法确认最新版本")
	}
	marker := "/releases/tag/"
	index := strings.LastIndex(response.Request.URL.Path, marker)
	if index < 0 {
		return releasePayload{}, errors.New("GitHub 最新发布页没有返回版本号")
	}
	tag, err := url.PathUnescape(strings.Trim(response.Request.URL.Path[index+len(marker):], "/"))
	valid := releaseTagPattern.MatchString(tag)
	if repository == ResumeDetectiveRepo {
		valid = semverPattern.MatchString(tag)
	}
	if err != nil || !valid {
		return releasePayload{}, errors.New("GitHub 最新发布页返回了无效版本号")
	}
	return releasePayload{TagName: tag, Name: tag, HTMLURL: response.Request.URL.String()}, nil
}

func (s *Service) Download(ctx context.Context) (Download, error) {
	if err := os.MkdirAll(s.UpdatesDir, 0o700); err != nil {
		return Download{}, err
	}
	info, release, asset, err := s.releaseAsset(ctx)
	if err != nil {
		return Download{}, err
	}
	if !info.Available {
		return Download{}, errors.New("当前已经是最新版")
	}
	expected, ok := normalizedDigest(asset.Digest)
	if !ok {
		return Download{}, errors.New("更新包没有可验证的 SHA-256 digest")
	}
	parsed, err := url.Parse(asset.BrowserDownloadURL)
	if err != nil || parsed.Scheme != "https" || !trustedHost(parsed.Hostname()) {
		return Download{}, errors.New("更新包地址不受信任")
	}
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	req.Header.Set("Accept", "application/octet-stream")
	req.Header.Set("User-Agent", "ResumeDetective-Updater/4")
	resp, err := s.Client.Do(req)
	if err != nil {
		return Download{}, fmt.Errorf("下载更新失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return Download{}, fmt.Errorf("下载更新返回 %d", resp.StatusCode)
	}
	if resp.ContentLength > maxUpdateBytes {
		return Download{}, errors.New("更新包超过大小限制")
	}
	temp, err := os.CreateTemp(s.UpdatesDir, ".download-*.tmp")
	if err != nil {
		return Download{}, err
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	hash := sha256.New()
	written, err := io.Copy(io.MultiWriter(temp, hash), io.LimitReader(resp.Body, maxUpdateBytes+1))
	if closeErr := temp.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return Download{}, err
	}
	if written > maxUpdateBytes {
		return Download{}, errors.New("更新包超过大小限制")
	}
	actual := hex.EncodeToString(hash.Sum(nil))
	if actual != expected {
		return Download{}, errors.New("更新包 SHA-256 校验失败")
	}
	final := filepath.Join(s.UpdatesDir, safeVersion(release.TagName)+"-"+filepath.Base(asset.Name))
	if err := os.Rename(tempPath, final); err != nil {
		return Download{}, err
	}
	return Download{Version: release.TagName, Path: final, SHA256: actual, Size: written}, nil
}

func (s *Service) StartInstall(download Download) error {
	relative, err := filepath.Rel(s.UpdatesDir, download.Path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return errors.New("更新包不在受信任的缓存目录")
	}
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	helper := filepath.Join(s.UpdatesDir, "ResumeDetectiveUpdateHelper-"+time.Now().Format("20060102-150405")+".exe")
	if err := copyFile(executable, helper); err != nil {
		return err
	}
	cmd := exec.Command(helper, "--apply-update", download.Path, "--update-target", executable, "--update-sha256", download.SHA256)
	cmd.Dir = filepath.Dir(executable)
	return cmd.Start()
}

func ApplyPackage(packagePath, target, expectedSHA string) error {
	actual, err := fileSHA256(packagePath)
	if err != nil {
		return err
	}
	if strings.ToLower(strings.TrimSpace(expectedSHA)) != actual {
		return errors.New("待安装更新包校验失败")
	}
	reader, err := zip.OpenReader(packagePath)
	if err != nil {
		return errors.New("更新包不是有效 ZIP")
	}
	defer reader.Close()
	var executable *zip.File
	for _, file := range reader.File {
		clean := filepath.ToSlash(filepath.Clean(file.Name))
		if strings.HasPrefix(clean, "../") || strings.HasPrefix(clean, "/") {
			return errors.New("更新包包含不安全路径")
		}
		if strings.EqualFold(filepath.Base(clean), "ResumeDetective.exe") && !file.FileInfo().IsDir() {
			executable = file
		}
	}
	if executable == nil || executable.UncompressedSize64 > uint64(maxUpdateBytes) {
		return errors.New("更新包缺少有效的 ResumeDetective.exe")
	}
	stage, err := os.CreateTemp(filepath.Dir(target), ".resumedetective-new-*.exe")
	if err != nil {
		return err
	}
	stagePath := stage.Name()
	defer os.Remove(stagePath)
	source, err := executable.Open()
	if err != nil {
		stage.Close()
		return err
	}
	_, copyErr := io.Copy(stage, io.LimitReader(source, maxUpdateBytes+1))
	source.Close()
	closeErr := stage.Close()
	if copyErr != nil {
		return copyErr
	}
	if closeErr != nil {
		return closeErr
	}
	backup := target + ".previous-" + time.Now().Format("20060102-150405") + ".exe"
	deadline := time.Now().Add(45 * time.Second)
	for {
		if err := os.Rename(target, backup); err == nil {
			break
		}
		if time.Now().After(deadline) {
			return errors.New("等待旧程序退出超时，更新未应用")
		}
		time.Sleep(500 * time.Millisecond)
	}
	if err := os.Rename(stagePath, target); err != nil {
		_ = os.Rename(backup, target)
		return err
	}
	cmd := exec.Command(target)
	cmd.Dir = filepath.Dir(target)
	return cmd.Start()
}

func (s *Service) releaseAsset(ctx context.Context) (Info, releasePayload, *Asset, error) {
	endpoint := strings.TrimRight(s.APIBase, "/") + "/repos/" + ResumeDetectiveRepo + "/releases/latest"
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2026-03-10")
	req.Header.Set("User-Agent", "ResumeDetective-Updater/4")
	resp, err := s.Client.Do(req)
	if err != nil {
		return Info{}, releasePayload{}, nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return Info{}, releasePayload{}, nil, fmt.Errorf("GitHub Release 返回 %d", resp.StatusCode)
	}
	var release releasePayload
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxReleaseResponse)).Decode(&release); err != nil {
		return Info{}, releasePayload{}, nil, err
	}
	comparison, ok := compareVersions(s.CurrentVersion, release.TagName)
	info := Info{Current: s.CurrentVersion, Latest: release.TagName, Available: ok && comparison < 0, ReleaseURL: release.HTMLURL}
	asset := selectWindowsAsset(release.Assets)
	if asset == nil {
		return info, release, nil, errors.New("Release 中没有 Windows x64 ZIP")
	}
	return info, release, asset, nil
}

func selectWindowsAsset(assets []Asset) *Asset {
	for i := range assets {
		name := strings.ToLower(assets[i].Name)
		if strings.HasSuffix(name, ".zip") && strings.Contains(name, "resumedetective") && (strings.Contains(name, "windows") || strings.Contains(name, "win")) && (strings.Contains(name, "x64") || strings.Contains(name, "amd64")) {
			return &assets[i]
		}
	}
	return nil
}
func normalizedDigest(value string) (string, bool) {
	value = strings.ToLower(strings.TrimSpace(strings.TrimPrefix(value, "sha256:")))
	return value, len(value) == 64 && isHex(value)
}
func isHex(value string) bool { _, err := hex.DecodeString(value); return err == nil }
func trustedHost(host string) bool {
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	return host == "api.github.com" || host == "github.com" || strings.HasSuffix(host, ".githubusercontent.com")
}
func safeVersion(v string) string {
	return strings.Map(func(r rune) rune {
		if r >= '0' && r <= '9' || r >= 'A' && r <= 'Z' || r >= 'a' && r <= 'z' || r == '.' || r == '-' {
			return r
		}
		return '-'
	}, v)
}
func compareVersions(current, latest string) (int, bool) {
	a, ok := versionParts(current)
	if !ok {
		return 0, false
	}
	b, ok := versionParts(latest)
	if !ok {
		return 0, false
	}
	for i := 0; i < 3; i++ {
		if a[i] < b[i] {
			return -1, true
		}
		if a[i] > b[i] {
			return 1, true
		}
	}
	return 0, true
}
func versionParts(value string) ([3]int, bool) {
	match := semverPattern.FindStringSubmatch(strings.TrimSpace(value))
	if match == nil {
		return [3]int{}, false
	}
	var out [3]int
	for i := 0; i < 3; i++ {
		out[i], _ = strconv.Atoi(match[i+1])
	}
	return out, true
}
func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
func copyFile(source, destination string) error {
	src, err := os.Open(source)
	if err != nil {
		return err
	}
	defer src.Close()
	temp, err := os.CreateTemp(filepath.Dir(destination), ".helper-*.tmp")
	if err != nil {
		return err
	}
	name := temp.Name()
	defer os.Remove(name)
	if _, err = io.Copy(temp, src); err != nil {
		temp.Close()
		return err
	}
	if err = temp.Close(); err != nil {
		return err
	}
	if runtime.GOOS != "windows" {
		_ = os.Chmod(name, 0o755)
	}
	return os.Rename(name, destination)
}
