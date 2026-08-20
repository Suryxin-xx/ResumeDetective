package update

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	xproxy "golang.org/x/net/proxy"
)

type NetworkConfig struct {
	Mode     string
	ProxyURL string
}

type NetworkTest struct {
	OK         bool   `json:"ok"`
	Mode       string `json:"mode"`
	Proxy      string `json:"proxy,omitempty"`
	Target     string `json:"target"`
	StatusCode int    `json:"statusCode,omitempty"`
	Message    string `json:"message"`
}

func (s *Service) TestNetwork(ctx context.Context, cfg NetworkConfig) (NetworkTest, error) {
	client, proxyAddress, err := newHTTPClient(cfg, 8*time.Second)
	mode := strings.ToLower(strings.TrimSpace(cfg.Mode))
	if mode == "" {
		mode = "auto"
	}
	result := NetworkTest{Mode: mode, Proxy: proxyAddress, Target: "api.github.com"}
	if err != nil {
		return result, err
	}
	defer client.CloseIdleConnections()
	target := "https://api.github.com/repos/" + ResumeDetectiveRepo + "/releases/latest"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	if err != nil {
		return result, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "ResumeDetective-Network-Test/4")
	resp, err := client.Do(req)
	if err != nil {
		result.Message = friendlyNetworkError(err)
		return result, nil
	}
	defer resp.Body.Close()
	result.StatusCode = resp.StatusCode
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		result.OK = true
		result.Message = "已成功连接 GitHub 更新服务"
		return result, nil
	}
	if resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusTooManyRequests {
		result.OK = true
		result.Message = "网络连接正常，但 GitHub API 当前受到限流"
		return result, nil
	}
	result.Message = fmt.Sprintf("已连接 GitHub，但服务返回 HTTP %d", resp.StatusCode)
	return result, nil
}

func friendlyNetworkError(err error) string {
	message := strings.ToLower(err.Error())
	switch {
	case errors.Is(err, context.DeadlineExceeded), strings.Contains(message, "timeout"):
		return "连接超时，请检查代理是否启用、端口是否正确"
	case strings.Contains(message, "connection refused"):
		return "代理连接被拒绝，请确认代理软件正在运行且端口正确"
	case strings.Contains(message, "no such host"):
		return "域名解析失败，请检查网络或代理的 DNS 设置"
	case strings.Contains(message, "proxyconnect"):
		return "无法连接代理服务器，请检查代理地址"
	default:
		return "无法访问 GitHub 更新服务，请检查代理规则、节点状态或网络连接"
	}
}

func newHTTPClient(cfg NetworkConfig, timeout time.Duration) (*http.Client, string, error) {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	mode := strings.ToLower(strings.TrimSpace(cfg.Mode))
	if mode == "" {
		mode = "auto"
	}
	proxyAddress := ""
	switch mode {
	case "off":
		transport.Proxy = nil
	case "env":
		transport.Proxy = http.ProxyFromEnvironment
		proxyAddress = environmentProxySummary()
	case "system":
		var err error
		proxyAddress, err = systemProxyURL()
		if err != nil {
			return nil, "", err
		}
		if proxyAddress == "" {
			return nil, "", errors.New("Windows 系统代理未启用或未配置固定代理地址")
		}
		if err := applyProxy(transport, proxyAddress); err != nil {
			return nil, "", err
		}
	case "custom":
		proxyAddress = strings.TrimSpace(cfg.ProxyURL)
		if proxyAddress == "" {
			return nil, "", errors.New("请填写自定义代理地址")
		}
		if err := applyProxy(transport, proxyAddress); err != nil {
			return nil, "", err
		}
	case "auto":
		proxyAddress = environmentProxySummary()
		if proxyAddress != "" {
			transport.Proxy = http.ProxyFromEnvironment
		} else if address, err := systemProxyURL(); err == nil && address != "" {
			proxyAddress = address
			if err := applyProxy(transport, address); err != nil {
				return nil, "", err
			}
		} else {
			transport.Proxy = nil
		}
	default:
		return nil, "", fmt.Errorf("不支持的更新网络模式 %q", mode)
	}
	client := &http.Client{Transport: transport, Timeout: timeout}
	client.CheckRedirect = secureRedirect
	return client, redactProxy(proxyAddress), nil
}

func applyProxy(transport *http.Transport, address string) error {
	address = strings.TrimSpace(address)
	if !strings.Contains(address, "://") {
		address = "http://" + address
	}
	parsed, err := url.Parse(address)
	if err != nil || parsed.Hostname() == "" {
		return errors.New("代理地址格式不正确")
	}
	switch strings.ToLower(parsed.Scheme) {
	case "http", "https":
		transport.Proxy = http.ProxyURL(parsed)
	case "socks5", "socks5h":
		var auth *xproxy.Auth
		if parsed.User != nil {
			password, _ := parsed.User.Password()
			auth = &xproxy.Auth{User: parsed.User.Username(), Password: password}
		}
		dialer, err := xproxy.SOCKS5("tcp", parsed.Host, auth, &net.Dialer{Timeout: 8 * time.Second, KeepAlive: 30 * time.Second})
		if err != nil {
			return fmt.Errorf("创建 SOCKS5 代理失败: %w", err)
		}
		transport.Proxy = nil
		transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
			return dialer.Dial(network, address)
		}
	default:
		return errors.New("代理仅支持 HTTP、HTTPS、SOCKS5 或 SOCKS5H")
	}
	return nil
}

func environmentProxySummary() string {
	for _, key := range []string{"HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"} {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}
	return ""
}

func redactProxy(value string) string {
	if value == "" {
		return ""
	}
	if !strings.Contains(value, "://") {
		value = "http://" + value
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.Host == "" {
		return value
	}
	parsed.User = nil
	return parsed.String()
}

func secureRedirect(req *http.Request, via []*http.Request) error {
	if len(via) > 8 || req.URL == nil || req.URL.Scheme != "https" || !trustedHost(req.URL.Hostname()) {
		return errors.New("更新下载重定向到了不受信任的地址")
	}
	return nil
}
