//go:build windows

package tray

import (
	"runtime"

	"fyne.io/systray"
)

type Actions struct {
	Open         func()
	Restart      func()
	CheckUpdates func()
	Quit         func()
}

func Run(icon []byte, tooltip, url string, actions Actions) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	systray.Run(func() {
		systray.SetIcon(icon)
		systray.SetTitle("ResumeDetective")
		systray.SetTooltip(tooltip)
		if actions.Open != nil {
			systray.SetOnTapped(func() { go actions.Open() })
		}
		openItem := systray.AddMenuItem("打开秋招工作台", "在浏览器中打开 "+url)
		addressItem := systray.AddMenuItem("运行地址："+url, "复制或在浏览器访问")
		addressItem.Disable()
		systray.AddSeparator()
		updateItem := systray.AddMenuItem("检查更新", "检查 ResumeDetective 新版本")
		restartItem := systray.AddMenuItem("重启服务", "重新启动本地网页服务")
		systray.AddSeparator()
		quitItem := systray.AddMenuItem("退出 ResumeDetective", "停止本地服务并退出")

		go menuLoop(openItem.ClickedCh, actions.Open)
		go menuLoop(updateItem.ClickedCh, actions.CheckUpdates)
		go menuLoop(restartItem.ClickedCh, actions.Restart)
		go menuLoop(quitItem.ClickedCh, actions.Quit)
	}, func() {})
}

func Quit() { systray.Quit() }

func menuLoop(clicks <-chan struct{}, action func()) {
	for range clicks {
		if action != nil {
			action()
		}
	}
}
