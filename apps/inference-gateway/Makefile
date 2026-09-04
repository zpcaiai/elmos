.PHONY: all build test clean

all: build test

build:
	mkdir -p bin
	go build -ldflags="-s -w" -o bin/inference-gateway .

test:
	go test -v ./...

clean:
	rm -rf bin
