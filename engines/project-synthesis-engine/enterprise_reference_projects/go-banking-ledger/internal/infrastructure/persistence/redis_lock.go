package persistence

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// releaseLockLuaScript ensures atomic release only if the caller holds the matching token.
const releaseLockLuaScript = `
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
`

// extendLockLuaScript atomically extends TTL if the token matches.
const extendLockLuaScript = `
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
`

// RedisLockHandle implements LockHandle for Redis-backed distributed locks.
type RedisLockHandle struct {
	resourceKey string
	token       string
	fencingSeq  int64
	expiry      time.Time
	stopRenew   chan struct{}
	renewClosed bool
	mu          sync.Mutex
}

func (h *RedisLockHandle) Resource() string     { return h.resourceKey }
func (h *RedisLockHandle) Token() string        { return h.token }
func (h *RedisLockHandle) FencingToken() int64  { return h.fencingSeq }
func (h *RedisLockHandle) ExpiresAt() time.Time { return h.expiry }

func (h *RedisLockHandle) StopRenewal() {
	h.mu.Lock()
	defer h.mu.Unlock()
	if !h.renewClosed && h.stopRenew != nil {
		close(h.stopRenew)
		h.renewClosed = true
	}
}

// RedisClusterLockManager implements DistributedLockManager with fencing tokens and heartbeat renewal.
type RedisClusterLockManager struct {
	client *redis.Client
}

func NewRedisClusterLockManager(client *redis.Client) *RedisClusterLockManager {
	return &RedisClusterLockManager{client: client}
}

func (m *RedisClusterLockManager) AcquireLock(ctx context.Context, resourceKey string, ttl time.Duration) (repository.LockHandle, error) {
	token := fmt.Sprintf("%s-%d", uuid.New().String(), time.Now().UnixNano())

	// Monotonically increment fencing token for resource
	fencingKey := fmt.Sprintf("%s:fencing_seq", resourceKey)
	fencingSeq, err := m.client.Incr(ctx, fencingKey).Result()
	if err != nil {
		return nil, fmt.Errorf("failed generating fencing token: %w", err)
	}

	success, err := m.client.SetNX(ctx, resourceKey, token, ttl).Result()
	if err != nil {
		return nil, fmt.Errorf("redis setnx error: %w", err)
	}
	if !success {
		return nil, fmt.Errorf("%w: resource %s held by another worker", repository.ErrLockAcquisition, resourceKey)
	}

	handle := &RedisLockHandle{
		resourceKey: resourceKey,
		token:       token,
		fencingSeq:  fencingSeq,
		expiry:      time.Now().UTC().Add(ttl),
		stopRenew:   make(chan struct{}),
	}

	// Launch background heartbeat renewal daemon (extends lock at 1/3 of TTL)
	go m.runHeartbeatDaemon(handle, ttl)

	return handle, nil
}

func (m *RedisClusterLockManager) runHeartbeatDaemon(h *RedisLockHandle, ttl time.Duration) {
	interval := ttl / 3
	if interval < 100*time.Millisecond {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-h.stopRenew:
			return
		case <-ticker.C:
			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			err := m.ExtendLock(ctx, h, ttl)
			cancel()
			if err != nil {
				// Lock lost or network partitioned
				return
			}
		}
	}
}

func (m *RedisClusterLockManager) ReleaseLock(ctx context.Context, handle repository.LockHandle) error {
	if rh, ok := handle.(*RedisLockHandle); ok {
		rh.StopRenewal()
	}

	res, err := m.client.Eval(ctx, releaseLockLuaScript, []string{handle.Resource()}, handle.Token()).Result()
	if err != nil {
		return err
	}
	if res == int64(0) {
		return repository.ErrLockLost
	}
	return nil
}

func (m *RedisClusterLockManager) ExtendLock(ctx context.Context, handle repository.LockHandle, additionalTTL time.Duration) error {
	ttlMs := additionalTTL.Milliseconds()
	res, err := m.client.Eval(ctx, extendLockLuaScript, []string{handle.Resource()}, handle.Token(), ttlMs).Result()
	if err != nil {
		return err
	}
	if res == int64(0) {
		return repository.ErrLockLost
	}
	return nil
}
