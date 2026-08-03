//go:build windows

package folderpicker

import (
	"context"
	"fmt"
	"runtime"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	fileOpenDialogOptions = 0x00000020 | // FOS_PICKFOLDERS
		0x00000040 | // FOS_FORCEFILESYSTEM
		0x00000800 | // FOS_PATHMUSTEXIST
		0x02000000 // FOS_DONTADDTORECENT
	sigdnFileSystemPath = 0x80058000
	hresultCanceled     = 0x800704C7
)

var (
	clsidFileOpenDialog  = windows.GUID{Data1: 0xDC1C5A9C, Data2: 0xE88A, Data3: 0x4DDE, Data4: [8]byte{0xA5, 0xA1, 0x60, 0xF8, 0x2A, 0x20, 0xAE, 0xF7}}
	iidIFileOpenDialog   = windows.GUID{Data1: 0xD57C7288, Data2: 0xD4AD, Data3: 0x4768, Data4: [8]byte{0xBE, 0x02, 0x9D, 0x96, 0x95, 0x32, 0xD9, 0x60}}
	ole32                = windows.NewLazySystemDLL("ole32.dll")
	user32               = windows.NewLazySystemDLL("user32.dll")
	procCoCreateInstance = ole32.NewProc("CoCreateInstance")
	procCoInitializeEx   = ole32.NewProc("CoInitializeEx")
	procCoUninitialize   = ole32.NewProc("CoUninitialize")
	procGetForeground    = user32.NewProc("GetForegroundWindow")
)

type fileDialog struct {
	vtbl *fileDialogVtbl
}

type fileDialogVtbl struct {
	queryInterface, addRef, release                  uintptr
	show                                             uintptr
	setFileTypes, setFileTypeIndex, getFileTypeIndex uintptr
	advise, unadvise                                 uintptr
	setOptions, getOptions                           uintptr
	setDefaultFolder, setFolder, getFolder           uintptr
	getCurrentSelection                              uintptr
	setFileName, getFileName, setTitle               uintptr
	setOKButtonLabel, setFileNameLabel               uintptr
	getResult                                        uintptr
}

type shellItem struct {
	vtbl *shellItemVtbl
}

type shellItemVtbl struct {
	queryInterface, addRef, release uintptr
	bindToHandler, getParent        uintptr
	getDisplayName                  uintptr
}

// Pick opens the native Windows IFileDialog in folder-selection mode. The call
// runs on a dedicated STA thread because Shell dialogs are COM apartment-bound.
func Pick(ctx context.Context) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	hr, _, _ := procCoInitializeEx.Call(0, windows.COINIT_APARTMENTTHREADED)
	if hresultFailed(hr) {
		return "", hresultError("初始化 Windows 文件夹选择器", hr)
	}
	defer procCoUninitialize.Call()

	var dialog *fileDialog
	hr, _, _ = procCoCreateInstance.Call(
		uintptr(unsafe.Pointer(&clsidFileOpenDialog)),
		0,
		windows.CLSCTX_INPROC_SERVER,
		uintptr(unsafe.Pointer(&iidIFileOpenDialog)),
		uintptr(unsafe.Pointer(&dialog)),
	)
	if hresultFailed(hr) || dialog == nil {
		return "", hresultError("创建 Windows 文件夹选择器", hr)
	}
	defer syscall.SyscallN(dialog.vtbl.release, uintptr(unsafe.Pointer(dialog)))

	var options uint32
	hr, _, _ = syscall.SyscallN(dialog.vtbl.getOptions, uintptr(unsafe.Pointer(dialog)), uintptr(unsafe.Pointer(&options)))
	if hresultFailed(hr) {
		return "", hresultError("读取文件夹选择选项", hr)
	}
	hr, _, _ = syscall.SyscallN(dialog.vtbl.setOptions, uintptr(unsafe.Pointer(dialog)), uintptr(options|fileOpenDialogOptions))
	if hresultFailed(hr) {
		return "", hresultError("设置文件夹选择选项", hr)
	}
	title, _ := windows.UTF16PtrFromString("选择 Python v3 数据目录（其中应包含 data.db）")
	hr, _, _ = syscall.SyscallN(dialog.vtbl.setTitle, uintptr(unsafe.Pointer(dialog)), uintptr(unsafe.Pointer(title)))
	if hresultFailed(hr) {
		return "", hresultError("设置文件夹选择窗口标题", hr)
	}

	owner, _, _ := procGetForeground.Call()
	hr, _, _ = syscall.SyscallN(dialog.vtbl.show, uintptr(unsafe.Pointer(dialog)), owner)
	if uint32(hr) == hresultCanceled {
		return "", nil
	}
	if hresultFailed(hr) {
		return "", hresultError("显示 Windows 文件夹选择器", hr)
	}

	var item *shellItem
	hr, _, _ = syscall.SyscallN(dialog.vtbl.getResult, uintptr(unsafe.Pointer(dialog)), uintptr(unsafe.Pointer(&item)))
	if hresultFailed(hr) || item == nil {
		return "", hresultError("读取所选文件夹", hr)
	}
	defer syscall.SyscallN(item.vtbl.release, uintptr(unsafe.Pointer(item)))

	var path *uint16
	hr, _, _ = syscall.SyscallN(item.vtbl.getDisplayName, uintptr(unsafe.Pointer(item)), sigdnFileSystemPath, uintptr(unsafe.Pointer(&path)))
	if hresultFailed(hr) || path == nil {
		return "", hresultError("读取所选文件夹路径", hr)
	}
	defer windows.CoTaskMemFree(unsafe.Pointer(path))
	return windows.UTF16PtrToString(path), nil
}

func hresultFailed(value uintptr) bool {
	return uint32(value)&0x80000000 != 0
}

func hresultError(action string, value uintptr) error {
	return fmt.Errorf("%s失败（HRESULT 0x%08X）", action, uint32(value))
}
