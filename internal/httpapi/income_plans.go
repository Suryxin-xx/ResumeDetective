package httpapi

import (
	"github.com/Suryxin-xx/ResumeDetective/internal/store"
	"net/http"
)

func (s *Server) listIncomePlans(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListIncomePlans(r.Context())
	if err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) saveIncomePlan(w http.ResponseWriter, r *http.Request) {
	var in store.IncomePlan
	if decodeJSON(w, r, &in) != nil {
		return
	}
	id, err := s.store.SaveIncomePlan(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]int64{"id": id})
}
func (s *Server) deleteIncomePlan(w http.ResponseWriter, r *http.Request) {
	id, err := store.ParseID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err = s.store.DeleteIncomePlan(r.Context(), id); err != nil {
		s.internalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
