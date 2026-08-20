//go:build windows

package update

import "testing"

func TestSelectSystemProxy(t *testing.T) {
	tests := map[string]string{
		"127.0.0.1:7890":                           "127.0.0.1:7890",
		"http=127.0.0.1:8080;https=127.0.0.1:8443": "127.0.0.1:8443",
		"http=127.0.0.1:8080;socks=127.0.0.1:1080": "127.0.0.1:8080",
		"socks=127.0.0.1:1080":                     "socks5://127.0.0.1:1080",
	}
	for input, want := range tests {
		if got := selectSystemProxy(input); got != want {
			t.Fatalf("selectSystemProxy(%q) = %q, want %q", input, got, want)
		}
	}
}
