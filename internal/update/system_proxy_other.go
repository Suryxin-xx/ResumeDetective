//go:build !windows

package update

func systemProxyURL() (string, error) { return "", nil }
