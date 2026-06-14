package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/keepalive"

	"github.com/dwilson/request-auth/db"
	"github.com/dwilson/request-auth/metrics"
	"github.com/dwilson/request-auth/pool"
	pb "github.com/dwilson/request-auth/proto"
	"github.com/dwilson/request-auth/service"
	"github.com/dwilson/request-auth/status"
)

func main() {
	databaseURL := envOr("DATABASE_URL", "")
	grpcAddr := envOr("GRPC_ADDR", ":9000")
	statusAddr := envOr("STATUS_ADDR", ":9003")

	if databaseURL == "" {
		log.Fatal("DATABASE_URL is required")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	dbClient, err := db.New(databaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}

	inst, shutdown, err := metrics.Init(ctx)
	if err != nil {
		log.Printf("otel init failed (metrics disabled): %v", err)
		inst = metrics.NewNoop()
	}
	defer shutdown()

	manager, err := pool.NewManager(dbClient, inst)
	if err != nil {
		log.Fatalf("pool manager: %v", err)
	}

	// gRPC server
	lis, err := net.Listen("tcp", grpcAddr)
	if err != nil {
		log.Fatalf("listen %s: %v", grpcAddr, err)
	}
	grpcSrv := grpc.NewServer(
		grpc.KeepaliveParams(keepalive.ServerParameters{
			MaxConnectionIdle: 5 * time.Minute,
			Time:              30 * time.Second,
			Timeout:           10 * time.Second,
		}),
		grpc.KeepaliveEnforcementPolicy(keepalive.EnforcementPolicy{
			MinTime:             10 * time.Second,
			PermitWithoutStream: true,
		}),
	)
	pb.RegisterPermitServiceServer(grpcSrv, service.NewPermitService(manager, inst))

	// HTTP status server
	mux := http.NewServeMux()
	mux.HandleFunc("/status", status.Handler(manager))
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprintln(w, `{"status":"ok"}`)
	})
	httpSrv := &http.Server{Addr: statusAddr, Handler: mux}

	go func() {
		log.Printf("gRPC listening on %s", grpcAddr)
		if err := grpcSrv.Serve(lis); err != nil {
			log.Printf("grpc: %v", err)
		}
	}()
	go func() {
		log.Printf("HTTP status on %s", statusAddr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("http: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("shutting down")
	grpcSrv.GracefulStop()
	_ = httpSrv.Shutdown(context.Background())
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
