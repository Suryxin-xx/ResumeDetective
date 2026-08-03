package ai

import (
	"context"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"github.com/Suryxin-xx/ResumeDetective/internal/settings"
)

func TestDirectConnectionUsesBearerHeader(t *testing.T) {
	t.Setenv("DEEPSEEK_API_KEY", "test-only-key")
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/models" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer test-only-key" {
			t.Fatalf("unexpected authorization header")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer server.Close()

	dir := t.TempDir()
	manager, err := settings.Open(filepath.Join(dir, "config.json"), filepath.Join(dir, ".env"))
	if err != nil {
		t.Fatal(err)
	}
	cfg := manager.Get()
	cfg.AI.BaseURL = server.URL
	if err := manager.Save(cfg); err != nil {
		t.Fatal(err)
	}
	service := New(nil, manager, dir)
	service.client = server.Client()
	result, err := service.Test(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !result.OK || result.Provider != "deepseek" {
		t.Fatalf("unexpected test result: %+v", result)
	}
}

func TestBalanceUsesOfficialEndpointAndNormalizesResponse(t *testing.T) {
	t.Setenv("DEEPSEEK_API_KEY", "balance-test-key")
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/user/balance" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer balance-test-key" {
			t.Fatalf("unexpected authorization header")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"12.34","granted_balance":"2.34","topped_up_balance":"10.00"}]}`))
	}))
	defer server.Close()

	dir := t.TempDir()
	manager, err := settings.Open(filepath.Join(dir, "config.json"), filepath.Join(dir, ".env"))
	if err != nil {
		t.Fatal(err)
	}
	cfg := manager.Get()
	cfg.AI.BaseURL = server.URL
	if err := manager.Save(cfg); err != nil {
		t.Fatal(err)
	}
	service := New(nil, manager, dir)
	service.client = server.Client()
	result, err := service.Balance(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !result.Available || len(result.Balances) != 1 || result.Balances[0].TotalBalance != "12.34" {
		t.Fatalf("unexpected balance result: %+v", result)
	}
}

func TestJoinEndpointRequiresSafeHTTPSURL(t *testing.T) {
	for _, value := range []string{"http://api.example.com", "https://user:pass@api.example.com", "not-a-url"} {
		if _, err := joinEndpoint(value, "models"); err == nil {
			t.Fatalf("expected %q to be rejected", value)
		}
	}
	got, err := joinEndpoint("https://api.deepseek.com/v1/", "/models")
	if err != nil || got != "https://api.deepseek.com/v1/models" {
		t.Fatalf("unexpected endpoint: %q, %v", got, err)
	}
}
