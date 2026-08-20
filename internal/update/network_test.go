package update

import (
	"strings"
	"testing"
	"time"
)

func TestCustomProxyValidation(t *testing.T) {
	for _, address := range []string{"http://127.0.0.1:7890", "https://proxy.example:8443", "socks5://127.0.0.1:7891"} {
		client, proxyAddress, err := newHTTPClient(NetworkConfig{Mode: "custom", ProxyURL: address}, time.Second)
		if err != nil {
			t.Fatalf("valid proxy %q was rejected: %v", address, err)
		}
		client.CloseIdleConnections()
		if proxyAddress != address {
			t.Fatalf("unexpected proxy summary %q for %q", proxyAddress, address)
		}
	}
	if _, _, err := newHTTPClient(NetworkConfig{Mode: "custom", ProxyURL: "ftp://127.0.0.1:21"}, time.Second); err == nil {
		t.Fatal("unsupported proxy scheme was accepted")
	}
}

func TestProxySummaryRemovesCredentials(t *testing.T) {
	client, summary, err := newHTTPClient(NetworkConfig{Mode: "custom", ProxyURL: "http://name:secret@127.0.0.1:7890"}, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	client.CloseIdleConnections()
	if strings.Contains(summary, "name") || strings.Contains(summary, "secret") {
		t.Fatalf("proxy credentials leaked in summary: %q", summary)
	}
}

func TestServiceClientUsesOperationTimeout(t *testing.T) {
	service := New("4.3.0", t.TempDir())
	client, err := service.clientWithTimeout(7 * time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if client.Timeout != 7*time.Minute {
		t.Fatalf("client timeout = %s, want 7m", client.Timeout)
	}
}
