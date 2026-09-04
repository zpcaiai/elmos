.PHONY: all build test clean run

all: build test

build:
	mkdir -p bin
	go build -ldflags="-s -w" -o bin/agent-gateway .

test:
	go test -v ./...

run: build
	./bin/agent-gateway

clean:
	rm -rf bin
