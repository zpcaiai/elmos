FROM golang:1.26.5-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/runner ./cmd/runner

FROM alpine:3.22
RUN addgroup -S runner && adduser -S runner -G runner && mkdir -p /work && chown runner:runner /work
COPY --from=build /out/runner /usr/local/bin/runner
USER runner
ENV RUNNER_WORK_ROOT=/work
ENTRYPOINT ["runner"]
