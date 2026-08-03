//go:build !windows

package tray

type Actions struct {
	Open         func()
	Restart      func()
	CheckUpdates func()
	Quit         func()
}

func Run(_ []byte, _, _ string, actions Actions) {
	if actions.Quit != nil {
		actions.Quit()
	}
}

func Quit() {}
