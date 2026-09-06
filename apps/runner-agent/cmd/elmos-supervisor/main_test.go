//go:build unix

package main

import (
	"bytes"
	"context"
	"io"
	"sync"
	"testing"
	"time"
)

func TestExitAndNoShellInterpolation(t *testing.T) {
	var out bytes.Buffer
	if code := supervise(context.Background(), []string{"/usr/bin/printf", "%s", "$(not-executed)"}, time.Millisecond, &out, io.Discard); code != 0 || out.String() != "$(not-executed)" {
		t.Fatalf("code=%d output=%q", code, out.String())
	}
	if code := supervise(context.Background(), []string{"/bin/sh", "-c", "exit 19"}, time.Millisecond, io.Discard, io.Discard); code != 19 {
		t.Fatal(code)
	}
}

func TestTimeoutKillsTermIgnoringGroupAndDoesNotWaitForPipes(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	start := time.Now()
	code := supervise(ctx, []string{"/bin/sh", "-c", "trap '' TERM; sleep 60 & wait"}, 20*time.Millisecond, io.Discard, io.Discard)
	if code != 124 || time.Since(start) > 3*time.Second {
		t.Fatalf("code=%d elapsed=%v", code, time.Since(start))
	}
}

func TestConcurrentLargeOutputDoesNotAccumulate(t *testing.T) {
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			code := supervise(context.Background(), []string{"/bin/sh", "-c", "dd if=/dev/zero bs=65536 count=64 2>/dev/null"}, time.Second, io.Discard, io.Discard)
			if code != 0 {
				t.Errorf("code=%d", code)
			}
		}()
	}
	wg.Wait()
}
