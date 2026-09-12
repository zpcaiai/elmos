.PHONY: all build test test-go test-py clean run-cli

BIN_DIR ?= bin
BINARY ?= $(BIN_DIR)/project-gen

all: build test

build:
	@mkdir -p $(BIN_DIR)
	go build -o $(BINARY) cmd/project-gen/main.go

test-go:
	go test -v ./...

test-py:
	uv run pytest tests/ -v

test: test-go test-py

clean:
	rm -rf $(BIN_DIR) .pytest_cache
