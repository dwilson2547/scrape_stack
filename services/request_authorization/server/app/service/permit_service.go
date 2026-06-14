package service

import (
	"io"
	"log"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/metric"

	"github.com/dwilson/request-auth/metrics"
	"github.com/dwilson/request-auth/pool"
	pb "github.com/dwilson/request-auth/proto"
)

type PermitService struct {
	pb.UnimplementedPermitServiceServer
	manager *pool.Manager
	inst    *metrics.Instruments
}

func NewPermitService(manager *pool.Manager, inst *metrics.Instruments) *PermitService {
	return &PermitService{manager: manager, inst: inst}
}

func (s *PermitService) PermitStream(stream pb.PermitService_PermitStreamServer) error {
	clientID := uuid.New().String()
	ctx := stream.Context()

	// All sends go through this channel so stream.Send is never called concurrently.
	sendCh := make(chan *pb.ServerMessage, 64)

	go func() {
		for msg := range sendCh {
			if err := stream.Send(msg); err != nil {
				log.Printf("send error client=%s: %v", clientID, err)
				return
			}
		}
	}()

	defer func() {
		s.manager.DisconnectClient(clientID)
		close(sendCh)
	}()

	for {
		in, err := stream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}

		switch p := in.Payload.(type) {
		case *pb.ClientMessage_Request:
			req := p.Request
			s.inst.PermitRequestTotal.Add(ctx, 1, metric.WithAttributes(metrics.DomainAttr(req.Domain)))
			s.inst.PermitQueued.Add(ctx, 1, metric.WithAttributes(metrics.DomainAttr(req.Domain)))
			waitStart := time.Now()

			go func() {
				grant, err := s.manager.Acquire(ctx, clientID, req.Domain, req.ReqId)

				waitMs := float64(time.Since(waitStart).Milliseconds())
				s.inst.PermitQueued.Add(ctx, -1, metric.WithAttributes(metrics.DomainAttr(req.Domain)))

				if err != nil {
					if ctx.Err() != nil {
						return
					}
					select {
					case sendCh <- &pb.ServerMessage{Payload: &pb.ServerMessage_Error{
						Error: &pb.ServerError{ReqId: req.ReqId, Message: err.Error()},
					}}:
					case <-ctx.Done():
					}
					return
				}

				s.inst.PermitWaitDuration.Record(ctx, waitMs,
					metric.WithAttributes(metrics.DomainAttr(req.Domain)))
				s.inst.PermitIssuedTotal.Add(ctx, 1,
					metric.WithAttributes(metrics.DomainAttr(req.Domain)))
				s.inst.PermitActive.Add(ctx, 1,
					metric.WithAttributes(metrics.DomainAttr(req.Domain)))

				select {
				case sendCh <- &pb.ServerMessage{Payload: &pb.ServerMessage_Grant{Grant: grant}}:
				case <-ctx.Done():
					s.manager.Return(grant.PermitId, 0)
					s.inst.PermitActive.Add(ctx, -1,
						metric.WithAttributes(metrics.DomainAttr(req.Domain)))
				}
			}()

		case *pb.ClientMessage_Ret:
			ret := p.Ret
			domain, holdDuration := s.manager.Return(ret.PermitId, ret.StatusCode)
			s.inst.PermitActive.Add(ctx, -1,
				metric.WithAttributes(metrics.DomainAttr(domain)))
			s.inst.PermitHoldDuration.Record(ctx, float64(holdDuration.Milliseconds()),
				metric.WithAttributes(metrics.DomainAttr(domain)))
			s.inst.ResponseStatusTotal.Add(ctx, 1,
				metric.WithAttributes(metrics.DomainAttr(domain), metrics.StatusAttr(ret.StatusCode)))
		}
	}
}
