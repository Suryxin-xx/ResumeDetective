// Command windows-resource writes ResumeDetective's icon, manifest and version
// metadata into an already-built Windows executable.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/tc-hib/winres"
	"github.com/tc-hib/winres/version"
)

func main() {
	var executable, iconPath, versionText string
	flag.StringVar(&executable, "exe", "", "Windows executable")
	flag.StringVar(&iconPath, "icon", "", "ICO file")
	flag.StringVar(&versionText, "version", "", "X.Y.Z version")
	flag.Parse()
	if err := stamp(executable, iconPath, versionText); err != nil {
		fmt.Fprintln(os.Stderr, "windows-resource:", err)
		os.Exit(1)
	}
}

func stamp(executable, iconPath, versionText string) error {
	if executable == "" || iconPath == "" || versionText == "" {
		return fmt.Errorf("exe, icon and version are required")
	}
	numeric, err := numericVersion(versionText)
	if err != nil {
		return err
	}
	iconFile, err := os.Open(iconPath)
	if err != nil {
		return err
	}
	ico, err := winres.LoadICO(iconFile)
	iconFile.Close()
	if err != nil {
		return err
	}
	resources := winres.ResourceSet{}
	if err := resources.SetIcon(winres.ID(1), ico); err != nil {
		return err
	}
	resources.SetManifest(winres.AppManifest{
		Identity:            winres.AssemblyIdentity{Name: "Suryxin.ResumeDetective", Version: numeric},
		Description:         "ResumeDetective 本地优先的求职进度工作台",
		ExecutionLevel:      winres.AsInvoker,
		DPIAwareness:        winres.DPIPerMonitorV2,
		LongPathAware:       true,
		UseCommonControlsV6: true,
	})
	info := version.Info{FileVersion: numeric, ProductVersion: numeric}
	fields := map[string]string{
		version.CompanyName: "Suryxin-xx", version.FileDescription: "ResumeDetective 求职进度工作台",
		version.FileVersion: versionText, version.InternalName: "ResumeDetective",
		version.LegalCopyright: "Copyright © 2026 Suryxin-xx", version.OriginalFilename: "ResumeDetective.exe",
		version.ProductName: "ResumeDetective", version.ProductVersion: versionText,
		version.Comments: "Local-first job application tracker. https://github.com/Suryxin-xx/ResumeDetective",
	}
	for key, value := range fields {
		if err := info.Set(version.LangDefault, key, value); err != nil {
			return err
		}
	}
	resources.SetVersionInfo(info)
	raw, err := os.ReadFile(executable)
	if err != nil {
		return err
	}
	var output bytes.Buffer
	if err := resources.WriteToEXE(&output, bytes.NewReader(raw)); err != nil {
		return err
	}
	temp, err := os.CreateTemp(filepath.Dir(executable), ".resumedetective-resource-*.exe")
	if err != nil {
		return err
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	if _, err := temp.Write(output.Bytes()); err != nil {
		temp.Close()
		return err
	}
	if err := temp.Close(); err != nil {
		return err
	}
	if err := os.Rename(executable, executable+".unstamped"); err != nil {
		return err
	}
	if err := os.Rename(tempPath, executable); err != nil {
		_ = os.Rename(executable+".unstamped", executable)
		return err
	}
	_ = os.Remove(executable + ".unstamped")
	return nil
}

func numericVersion(value string) ([4]uint16, error) {
	value = strings.TrimPrefix(strings.TrimSpace(value), "v")
	parts := strings.Split(value, ".")
	if len(parts) != 3 {
		return [4]uint16{}, fmt.Errorf("version must be X.Y.Z")
	}
	var result [4]uint16
	for index, part := range parts {
		parsed, err := strconv.ParseUint(part, 10, 16)
		if err != nil {
			return result, err
		}
		result[index] = uint16(parsed)
	}
	return result, nil
}
