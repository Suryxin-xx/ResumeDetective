//go:build !windows

package autostart

import "errors"

func (m *Manager) Set(enabled bool) error {
	if enabled {
		return errors.New("当前系统不支持 Windows 登录自启")
	}
	return nil
}
func (m *Manager) Enabled() (bool, error) { return false, nil }
