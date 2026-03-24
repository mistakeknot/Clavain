package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// sseEvent is a single SSE event ready to write.
type sseEvent struct {
	ID   int64  // monotonic event ID
	Type string // "snapshot", "delta", "heartbeat"
	Data []byte // JSON payload
}

// streamBroker fans out events to connected SSE clients.
type streamBroker struct {
	mu      sync.RWMutex
	clients map[chan sseEvent]struct{}
	seq     int64
}

func newStreamBroker() *streamBroker {
	return &streamBroker{
		clients: make(map[chan sseEvent]struct{}),
	}
}

func (b *streamBroker) subscribe() chan sseEvent {
	ch := make(chan sseEvent, 32) // buffer to avoid blocking broadcaster
	b.mu.Lock()
	b.clients[ch] = struct{}{}
	b.mu.Unlock()
	return ch
}

func (b *streamBroker) unsubscribe(ch chan sseEvent) {
	b.mu.Lock()
	delete(b.clients, ch)
	b.mu.Unlock()
	close(ch)
}

func (b *streamBroker) clientCount() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.clients)
}

func (b *streamBroker) broadcast(eventType string, data []byte) {
	b.mu.Lock()
	b.seq++
	evt := sseEvent{ID: b.seq, Type: eventType, Data: data}
	for ch := range b.clients {
		select {
		case ch <- evt:
		default:
			// Slow consumer — drop event rather than blocking
		}
	}
	b.mu.Unlock()
}

// cmdFactoryStream starts an SSE server streaming factory status.
func cmdFactoryStream(args []string) error {
	port := 8401
	interval := 5 * time.Second
	corsOrigins := "*"

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--port":
			if i+1 < len(args) {
				i++
				if p, err := strconv.Atoi(args[i]); err == nil {
					port = p
				}
			}
		case "--interval":
			if i+1 < len(args) {
				i++
				if d, err := time.ParseDuration(args[i]); err == nil {
					interval = d
				}
			}
		case "--cors-origins":
			if i+1 < len(args) {
				i++
				corsOrigins = args[i]
			}
		}
	}

	broker := newStreamBroker()
	startTime := time.Now()

	// Cache for latest snapshot (served to new connections)
	var (
		cacheMu   sync.RWMutex
		cacheData []byte
		cachePrev *factoryStatus
	)

	// Collector goroutine: gathers factory status on interval, broadcasts
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		heartbeatTicker := time.NewTicker(10 * time.Second)
		defer heartbeatTicker.Stop()

		// Immediate first collection
		collectAndBroadcast(broker, &cacheMu, &cacheData, &cachePrev)

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				collectAndBroadcast(broker, &cacheMu, &cacheData, &cachePrev)
			case <-heartbeatTicker.C:
				hb, _ := json.Marshal(map[string]interface{}{
					"ts":  time.Now().UTC().Format(time.RFC3339),
					"seq": broker.seq,
				})
				broker.broadcast("heartbeat", hb)
			}
		}
	}()

	// HTTP handlers
	mux := http.NewServeMux()

	mux.HandleFunc("/stream", func(w http.ResponseWriter, r *http.Request) {
		setCORSHeaders(w, r, corsOrigins)
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming not supported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("X-Accel-Buffering", "no") // disable nginx buffering

		// Send current snapshot immediately on connect
		cacheMu.RLock()
		initial := cacheData
		cacheMu.RUnlock()
		if initial != nil {
			writeSSEEvent(w, sseEvent{ID: 0, Type: "snapshot", Data: initial})
			flusher.Flush()
		}

		ch := broker.subscribe()
		defer broker.unsubscribe(ch)

		for {
			select {
			case <-r.Context().Done():
				return
			case evt, ok := <-ch:
				if !ok {
					return
				}
				writeSSEEvent(w, evt)
				flusher.Flush()
			}
		}
	})

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		setCORSHeaders(w, r, corsOrigins)
		w.Header().Set("Content-Type", "application/json")
		uptime := time.Since(startTime).Truncate(time.Second).String()
		fmt.Fprintf(w, `{"ok":true,"clients":%d,"uptime":"%s"}`, broker.clientCount(), uptime)
	})

	// Graceful shutdown
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%d", port),
		Handler: mux,
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		<-sigCh
		log.Println("factory-stream: shutting down...")
		cancel()
		shutCtx, shutCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutCancel()
		srv.Shutdown(shutCtx)
	}()

	log.Printf("factory-stream: listening on :%d (interval=%s, cors=%s)", port, interval, corsOrigins)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("factory-stream: %w", err)
	}
	return nil
}

// collectAndBroadcast gathers factory status, detects deltas, and broadcasts.
func collectAndBroadcast(broker *streamBroker, cacheMu *sync.RWMutex, cacheData *[]byte, cachePrev **factoryStatus) {
	status := gatherFactoryStatus()
	data, err := json.Marshal(status)
	if err != nil {
		return
	}

	// Detect agent status deltas
	cacheMu.RLock()
	prev := *cachePrev
	cacheMu.RUnlock()

	if prev != nil {
		deltas := detectFleetDeltas(prev, &status)
		for _, d := range deltas {
			dData, _ := json.Marshal(d)
			broker.broadcast("delta", dData)
		}
	}

	// Update cache
	cacheMu.Lock()
	*cacheData = data
	*cachePrev = &status
	cacheMu.Unlock()

	// Broadcast full snapshot
	broker.broadcast("snapshot", data)
}

// agentDelta describes a change in agent status.
type agentDelta struct {
	Type  string `json:"type"`
	Agent string `json:"agent"`
	From  string `json:"from"`
	To    string `json:"to"`
}

// detectFleetDeltas compares two snapshots and returns agent status changes.
func detectFleetDeltas(prev, curr *factoryStatus) []agentDelta {
	prevMap := make(map[string]bool, len(prev.Fleet.Agents))
	for _, a := range prev.Fleet.Agents {
		prevMap[a.SessionName] = a.Active
	}

	var deltas []agentDelta
	for _, a := range curr.Fleet.Agents {
		prevActive, existed := prevMap[a.SessionName]
		if !existed {
			deltas = append(deltas, agentDelta{
				Type: "agent_status", Agent: a.SessionName,
				From: "absent", To: statusStr(a.Active),
			})
		} else if prevActive != a.Active {
			deltas = append(deltas, agentDelta{
				Type: "agent_status", Agent: a.SessionName,
				From: statusStr(prevActive), To: statusStr(a.Active),
			})
		}
	}

	// Detect removed agents
	currMap := make(map[string]bool, len(curr.Fleet.Agents))
	for _, a := range curr.Fleet.Agents {
		currMap[a.SessionName] = true
	}
	for _, a := range prev.Fleet.Agents {
		if !currMap[a.SessionName] {
			deltas = append(deltas, agentDelta{
				Type: "agent_status", Agent: a.SessionName,
				From: statusStr(a.Active), To: "absent",
			})
		}
	}

	return deltas
}

func statusStr(active bool) string {
	if active {
		return "executing"
	}
	return "idle"
}

// writeSSEEvent writes a single SSE event to the response writer.
func writeSSEEvent(w http.ResponseWriter, evt sseEvent) {
	if evt.ID > 0 {
		fmt.Fprintf(w, "id: %d\n", evt.ID)
	}
	fmt.Fprintf(w, "event: %s\n", evt.Type)
	fmt.Fprintf(w, "data: %s\n\n", evt.Data)
}

// setCORSHeaders sets CORS headers for SSE/health endpoints.
func setCORSHeaders(w http.ResponseWriter, r *http.Request, corsOrigins string) {
	origin := r.Header.Get("Origin")
	if corsOrigins == "*" {
		w.Header().Set("Access-Control-Allow-Origin", "*")
	} else if origin != "" {
		for _, allowed := range strings.Split(corsOrigins, ",") {
			if strings.TrimSpace(allowed) == origin {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				break
			}
		}
	}
	w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID")
}
