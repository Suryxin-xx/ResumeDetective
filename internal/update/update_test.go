package update

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCompareVersions(t *testing.T) {
	tests := []struct {
		current string
		latest  string
		want    int
		ok      bool
	}{
		{"4.0.0", "v4.0.1", -1, true},
		{"v4.1.0", "4.0.9", 1, true},
		{"4.0.0", "4.0.0", 0, true},
		{"4.0.0-dev", "4.0.1", -1, true},
		{"development", "4.0.1", 0, false},
	}
	for _, test := range tests {
		got, ok := compareVersions(test.current, test.latest)
		if got != test.want || ok != test.ok {
			t.Fatalf("compareVersions(%q, %q) = (%d, %v), want (%d, %v)", test.current, test.latest, got, ok, test.want, test.ok)
		}
	}
}

func TestCheckSelectsVerifiedWindowsAsset(t *testing.T) {
	digest := strings.Repeat("a", 64)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"tag_name":"v4.1.0","name":"Stable","html_url":"https://github.com/Suryxin-xx/ResumeDetective/releases/tag/v4.1.0","assets":[{"name":"ResumeDetective-windows-x64.zip","browser_download_url":"https://github.com/download.zip","size":1024,"digest":"sha256:%s"}]}`, digest)
	}))
	defer server.Close()
	service := New("4.0.0", t.TempDir())
	service.APIBase = server.URL
	service.Client = server.Client()
	info, err := service.Check(context.Background(), ResumeDetectiveRepo)
	if err != nil {
		t.Fatal(err)
	}
	if !info.Available || !info.CanAutoUpdate || info.AssetName != "ResumeDetective-windows-x64.zip" {
		t.Fatalf("unexpected update info: %+v", info)
	}
}

func TestCheckFallsBackToOfficialReleasePageWhenAPIIsLimited(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/repos/" + ResumeDetectiveRepo + "/releases/latest":
			w.WriteHeader(http.StatusForbidden)
		case "/" + ResumeDetectiveRepo + "/releases/latest":
			http.Redirect(w, r, "/"+ResumeDetectiveRepo+"/releases/tag/v4.2.0", http.StatusFound)
		case "/" + ResumeDetectiveRepo + "/releases/tag/v4.2.0":
			w.WriteHeader(http.StatusOK)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	service := New("4.1.0", t.TempDir())
	service.APIBase = server.URL
	service.WebBase = server.URL
	service.Client = server.Client()
	info, err := service.Check(context.Background(), ResumeDetectiveRepo)
	if err != nil {
		t.Fatal(err)
	}
	if !info.Available || info.Latest != "v4.2.0" || info.CanAutoUpdate {
		t.Fatalf("unexpected fallback update info: %+v", info)
	}
	if !strings.Contains(info.Reason, "API") || !strings.Contains(info.ReleaseURL, "/releases/tag/v4.2.0") {
		t.Fatalf("fallback should explain the limitation and retain the release URL: %+v", info)
	}
}

func TestReasonixFallbackAcceptsDesktopReleaseTag(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/releases/latest") && strings.HasPrefix(r.URL.Path, "/repos/") {
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		if strings.HasSuffix(r.URL.Path, "/releases/latest") {
			http.Redirect(w, r, "/"+ReasonixRepo+"/releases/tag/desktop-v1.19.1", http.StatusFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()
	service := New("4.1.0", t.TempDir())
	service.APIBase, service.WebBase, service.Client = server.URL, server.URL, server.Client()
	info, err := service.Check(context.Background(), ReasonixRepo)
	if err != nil {
		t.Fatal(err)
	}
	if info.Latest != "desktop-v1.19.1" || !info.Available || info.CanAutoUpdate {
		t.Fatalf("unexpected Reasonix fallback info: %+v", info)
	}
}

func TestCheckFallsBackWhenGitHubAPIConnectionDrops(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/repos/") {
			hijacker, ok := w.(http.Hijacker)
			if !ok {
				t.Fatal("test server does not support hijacking")
			}
			connection, _, err := hijacker.Hijack()
			if err != nil {
				t.Fatal(err)
			}
			_ = connection.Close()
			return
		}
		if strings.HasSuffix(r.URL.Path, "/releases/latest") {
			http.Redirect(w, r, "/"+ResumeDetectiveRepo+"/releases/tag/v4.2.1", http.StatusFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()
	service := New("4.1.0", t.TempDir())
	service.APIBase, service.WebBase, service.Client = server.URL, server.URL, server.Client()
	info, err := service.Check(context.Background(), ResumeDetectiveRepo)
	if err != nil {
		t.Fatal(err)
	}
	if info.Latest != "v4.2.1" || !info.Available || !strings.Contains(info.Reason, "API") {
		t.Fatalf("unexpected connection fallback info: %+v", info)
	}
}

func TestApplyPackageRejectsWrongDigestBeforeChangingTarget(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "ResumeDetective.exe")
	if err := os.WriteFile(target, []byte("old"), 0o700); err != nil {
		t.Fatal(err)
	}
	packagePath := filepath.Join(dir, "update.zip")
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	file, err := writer.Create("ResumeDetective.exe")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = file.Write([]byte("new"))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(packagePath, buffer.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	wrong := sha256.Sum256([]byte("wrong"))
	err = ApplyPackage(packagePath, target, hex.EncodeToString(wrong[:]))
	if err == nil || !strings.Contains(err.Error(), "校验") {
		t.Fatalf("expected digest rejection, got %v", err)
	}
	content, readErr := os.ReadFile(target)
	if readErr != nil || string(content) != "old" {
		t.Fatalf("target was changed: %q, %v", content, readErr)
	}
}
