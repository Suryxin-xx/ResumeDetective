//go:build windows

package update

import (
	"errors"
	"strings"

	"golang.org/x/sys/windows/registry"
)

func systemProxyURL() (string, error) {
	key, err := registry.OpenKey(registry.CURRENT_USER, `Software\Microsoft\Windows\CurrentVersion\Internet Settings`, registry.QUERY_VALUE)
	if err != nil {
		return "", errors.New("无法读取 Windows 系统代理设置")
	}
	defer key.Close()
	enabled, _, err := key.GetIntegerValue("ProxyEnable")
	if err != nil || enabled == 0 {
		return "", nil
	}
	value, _, err := key.GetStringValue("ProxyServer")
	if err != nil {
		return "", errors.New("Windows 系统代理已启用，但没有可用的代理地址")
	}
	return selectSystemProxy(value), nil
}

func selectSystemProxy(value string) string {
	value = strings.TrimSpace(value)
	if !strings.Contains(value, "=") {
		return value
	}
	entries := map[string]string{}
	for _, part := range strings.Split(value, ";") {
		key, address, ok := strings.Cut(part, "=")
		if ok {
			entries[strings.ToLower(strings.TrimSpace(key))] = strings.TrimSpace(address)
		}
	}
	for _, key := range []string{"https", "http", "socks"} {
		if address := entries[key]; address != "" {
			if key == "socks" && !strings.Contains(address, "://") {
				return "socks5://" + address
			}
			return address
		}
	}
	return ""
}
