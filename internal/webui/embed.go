package webui

import (
	"embed"
	"io/fs"
)

//go:embed dist/*
var content embed.FS

func Files() (fs.FS, error) { return fs.Sub(content, "dist") }
