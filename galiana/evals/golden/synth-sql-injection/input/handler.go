package main

import (
	"database/sql"
	"fmt"
	"net/http"
)

var db *sql.DB

func getUserHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("id")
	// BUG: SQL injection — user input directly concatenated into query
	query := fmt.Sprintf("SELECT name, email FROM users WHERE id = '%s'", userID)
	row := db.QueryRow(query)

	var name, email string
	if err := row.Scan(&name, &email); err != nil {
		http.Error(w, "user not found", 404)
		return
	}
	fmt.Fprintf(w, "Name: %s, Email: %s", name, email)
}

func deleteUserHandler(w http.ResponseWriter, r *http.Request) {
	// BUG: No authentication check — anyone can delete users
	userID := r.URL.Query().Get("id")
	query := fmt.Sprintf("DELETE FROM users WHERE id = '%s'", userID)
	_, err := db.Exec(query)
	if err != nil {
		http.Error(w, "delete failed", 500)
		return
	}
	fmt.Fprintf(w, "User %s deleted", userID)
}

func main() {
	http.HandleFunc("/user", getUserHandler)
	http.HandleFunc("/user/delete", deleteUserHandler)
	http.ListenAndServe(":8080", nil)
}
