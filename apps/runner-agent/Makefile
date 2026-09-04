.PHONY: all build test clean

BIN_DIR := bin
BINARY := $(BIN_DIR)/runner-agent

all: test build

build:
	@mkdir -p $(BIN_DIR)
	go build -ldflags="-s -w" -o $(BINARY) .

test:
	go test -v -race ./...

clean:
	rm -rf $(BIN_DIR)
