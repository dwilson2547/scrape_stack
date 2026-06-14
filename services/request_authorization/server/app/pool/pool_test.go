package pool

import (
	"context"
	"testing"
	"time"

	pb "github.com/dwilson/request-auth/proto"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func testConfig(poolSize int) Config {
	return Config{
		PoolSize:          poolSize,
		BaseDelayMs:       0, // no delay in tests
		BackoffMultiplier: 3.0,
		MaxDelayMs:        60000,
		RecoveryThreshold: 10,
	}
}

func TestPool_AcquireImmediatelyWhenFree(t *testing.T) {
	p := NewPool("example.com", testConfig(1))
	grant, err := p.Acquire(context.Background(), "client-1", 1)
	require.NoError(t, err)
	assert.NotEmpty(t, grant.PermitId)
	assert.Equal(t, int64(1), grant.ReqId)
}

func TestPool_QueueWhenFull(t *testing.T) {
	p := NewPool("example.com", testConfig(1))

	grant1, err := p.Acquire(context.Background(), "client-1", 1)
	require.NoError(t, err)

	done := make(chan *pb.PermitGrant, 1)
	go func() {
		g, _ := p.Acquire(context.Background(), "client-2", 2)
		done <- g
	}()

	time.Sleep(20 * time.Millisecond)
	select {
	case <-done:
		t.Fatal("should still be waiting")
	default:
	}

	p.Return(grant1.PermitId, 200)

	select {
	case g := <-done:
		assert.NotNil(t, g)
		assert.Equal(t, int64(2), g.ReqId)
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for second grant")
	}
}

func TestPool_CancelledContextRemovesWaiter(t *testing.T) {
	p := NewPool("example.com", testConfig(1))
	_, _ = p.Acquire(context.Background(), "client-1", 1)

	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)
	go func() {
		_, err := p.Acquire(ctx, "client-2", 2)
		errCh <- err
	}()

	time.Sleep(20 * time.Millisecond)
	cancel()

	select {
	case err := <-errCh:
		assert.ErrorIs(t, err, context.Canceled)
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out")
	}

	status := p.Status()
	assert.Equal(t, 0, status.Queued)
}

func TestPool_DisconnectClientReturnsPermit(t *testing.T) {
	p := NewPool("example.com", testConfig(1))

	grant, err := p.Acquire(context.Background(), "client-1", 1)
	require.NoError(t, err)
	assert.True(t, p.HasPermit(grant.PermitId))

	done := make(chan *pb.PermitGrant, 1)
	go func() {
		g, _ := p.Acquire(context.Background(), "client-2", 2)
		done <- g
	}()

	time.Sleep(20 * time.Millisecond)
	p.DisconnectClient("client-1")
	assert.False(t, p.HasPermit(grant.PermitId))

	select {
	case g := <-done:
		assert.NotNil(t, g)
	case <-time.After(200 * time.Millisecond):
		t.Fatal("waiter not unblocked after disconnect")
	}
}

func TestPool_MultiSlotPool(t *testing.T) {
	p := NewPool("example.com", testConfig(3))

	grants := make([]*pb.PermitGrant, 3)
	for i := range grants {
		g, err := p.Acquire(context.Background(), "client-1", int64(i))
		require.NoError(t, err)
		grants[i] = g
	}

	status := p.Status()
	assert.Equal(t, 3, status.Active)
	assert.Equal(t, 0, status.Queued)
}
