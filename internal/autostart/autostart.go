package autostart

type Controller interface {
	Set(enabled bool) error
	Enabled() (bool, error)
}

type Manager struct {
	name string
}

func New(name string) *Manager { return &Manager{name: name} }
