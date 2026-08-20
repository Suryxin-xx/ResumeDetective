package settings

import "testing"

func TestNormalizeThemeAndNavigation(t *testing.T) {
	cfg := Defaults()
	cfg.Theme = "soft"
	cfg.NavigationOrder = []string{"settings", "applications", "applications", "unknown"}
	cfg.HiddenNavigation = []string{"offers", "overview", "unknown", "offers"}
	cfg.normalize()
	if cfg.Theme != "paper" {
		t.Fatalf("legacy soft theme should migrate to paper, got %q", cfg.Theme)
	}
	if len(cfg.NavigationOrder) != len(defaultNavigation) || cfg.NavigationOrder[0] != "settings" {
		t.Fatalf("navigation order was not normalized: %#v", cfg.NavigationOrder)
	}
	if len(cfg.HiddenNavigation) != 1 || cfg.HiddenNavigation[0] != "offers" {
		t.Fatalf("hidden navigation was not normalized: %#v", cfg.HiddenNavigation)
	}
}

func TestResumeNamingDefaultsAndLimit(t *testing.T) {
	cfg := Defaults()
	if cfg.ResumeNameTemplate != "{company}-{position}" || !cfg.AutoRenameResumes {
		t.Fatalf("unexpected resume naming defaults: %#v", cfg)
	}
	cfg.ResumeNameTemplate = ""
	cfg.normalize()
	if cfg.ResumeNameTemplate != DefaultResumeNameTemplate {
		t.Fatalf("empty template should use default, got %q", cfg.ResumeNameTemplate)
	}
}

func TestUpdateNetworkDefaultsAndNormalization(t *testing.T) {
	cfg := Defaults()
	if cfg.UpdateNetwork.Mode != "auto" || cfg.UpdateNetwork.ProxyURL != "" {
		t.Fatalf("unexpected update network defaults: %#v", cfg.UpdateNetwork)
	}
	cfg.UpdateNetwork.Mode = " UNKNOWN "
	cfg.UpdateNetwork.ProxyURL = "  http://127.0.0.1:7890  "
	cfg.normalize()
	if cfg.UpdateNetwork.Mode != "auto" || cfg.UpdateNetwork.ProxyURL != "http://127.0.0.1:7890" {
		t.Fatalf("update network was not normalized: %#v", cfg.UpdateNetwork)
	}
}
