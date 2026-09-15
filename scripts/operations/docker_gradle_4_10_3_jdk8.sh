#!/bin/sh
set -eu

cache_root="${ELMOS_SPRING_DOCKER_CACHE:-/private/tmp/elmos-spring-route-docker-cache}"
mkdir -p "$cache_root/gradle-4" "$cache_root/home-4"
exec docker run --rm \
  --name "elmos-spring-gradle4-$$" \
  --platform linux/arm64 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 512 \
  --memory 3g \
  --user "$(id -u):$(id -g)" \
  -e HOME=/cache/home \
  -e GRADLE_USER_HOME=/cache/gradle \
  -v "$PWD:$PWD" \
  -v "$cache_root:/cache" \
  -w "$PWD" \
  --entrypoint /opt/gradle/bin/gradle \
  gradle@sha256:665a76a6302b5724f305a99608229bdeeb0dc9d5e015e2ca565dbb1fa1be64d9 \
  "$@"
