# 执行矩阵

## Batch 66 — TypeScript and JavaScript

- `corepack enable`
- `pnpm install --frozen-lockfile`
- `pnpm lint`
- `pnpm test`
- `pnpm build`
- `pnpm exec playwright test`

## Batch 67 — Go Cloud-Native

- `go mod verify`
- `go vet ./...`
- `go test -race ./...`
- `go test -fuzz=Fuzz -fuzztime=30s ./...`
- `GOOS=linux GOARCH=amd64 go build ./...`

## Batch 68 — Kotlin JVM Android and Multiplatform

- `./gradlew --no-daemon test`
- `./gradlew detekt`
- `./gradlew lint`
- `./gradlew assemble`
- `./gradlew connectedCheck`

## Batch 69 — PHP Laravel Symfony and WordPress

- `composer validate --strict`
- `composer install --no-interaction`
- `vendor/bin/phpunit`
- `vendor/bin/phpstan analyse`
- `php artisan test`

## Batch 70 — C C++ Industrial and Native

- `cmake -S . -B build -G Ninja`
- `cmake --build build --parallel`
- `ctest --test-dir build --output-on-failure`
- `clang-tidy <sources>`
- `ASAN_OPTIONS=detect_leaks=1 ctest --test-dir build`

## Batch 71 — Rust Secure Systems

- `cargo fmt --check`
- `cargo clippy --all-targets --all-features -- -D warnings`
- `cargo test --all-features`
- `cargo audit`
- `cargo test --release`

## Batch 72 — Dart Flutter Multiplatform

- `flutter pub get`
- `flutter analyze`
- `flutter test`
- `flutter test integration_test`
- `flutter build <target>`

## Batch 73 — Swift Apple Native

- `swift package resolve`
- `swift test`
- `xcodebuild build`
- `xcodebuild test`
- `xcodebuild archive`

## Batch 74 — Bash Shell and PowerShell

- `shellcheck <scripts>`
- `bats tests`
- `pwsh -NoProfile -Command Invoke-Pester`
- `pwsh -NoProfile -Command Invoke-ScriptAnalyzer`

## Batch 75 — SQL and API Contract Languages

- `<database> migration test`
- `spectral lint openapi.yaml`
- `buf lint`
- `buf breaking --against <baseline>`
- `graphql-inspector diff <old> <new>`

## Batch 76 — Make CMake and Nginx

- `make -n`
- `make -j2 test`
- `cmake --build build --parallel`
- `nginx -t`
- `curl --fail --show-error <probe>`

## Batch 77 — Dockerfile and Docker Compose

- `docker buildx build --load .`
- `docker image inspect <image>`
- `docker compose config`
- `docker compose up --wait`
- `trivy image <image>`

## Batch 78 — HCL Terraform Kubernetes YAML and Helm

- `terraform fmt -check -recursive`
- `terraform validate`
- `terraform plan -out=tfplan`
- `kubectl apply --dry-run=server -f <dir>`
- `helm lint <chart>`
- `helm template <release> <chart>`

## Batch 79 — GitHub Actions GitLab CI and Jenkins

- `actionlint`
- `gitlab-ci-lint <pipeline>`
- `jenkinsfile-runner <pipeline>`
- `<provider> pipeline replay`
- `verify provenance and OIDC claims`

## Batch 80 — Polyglot Project Operations and Certification

- `./validate.sh`
- `./scripts/run_local_ci.sh`
- `./scripts/run_runtime_journeys.sh`
- `./scripts/verify_evidence.sh`
- `./scripts/run_release_gate.sh`
