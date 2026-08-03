//go:build !windows

package folderpicker

import (
	"context"
	"errors"
)

func Pick(context.Context) (string, error) {
	return "", errors.New("文件夹选择功能仅支持 Windows")
}
