# Project Generation & DDD Architecture Validator

Engineering application supporting multi-language project generation (Go, Python), Kubernetes/Helm manifests generation, and static DDD architectural validation.

## Features
- **Go Microservice Generator**: Generates clean Domain-Driven Design Go projects.
- **Python Microservice Generator**: Generates clean Domain-Driven Design Python projects.
- **Kubernetes & Helm Generator**: Produces K8s base, dev/prod overlays, and Helm chart.
- **DDD Architectural Validator**: Static analysis enforcing DDD layer isolation rules.

## CLI Usage (Go)
```bash
# Generate Go DDD project
./bin/project-gen new --lang go --name my-service --module example.com/my-service --port 8080 --out ./output/my-service

# Generate Python DDD project
./bin/project-gen new --lang python --name my-py-service --port 8000 --out ./output/my-py-service

# Generate K8s manifests and Helm chart
./bin/project-gen k8s --name my-service --port 8080 --replicas 3 --out ./output/k8s

# Validate DDD architecture
./bin/project-gen validate --path ./output/my-service --arch ddd
```

## CLI Usage (Python)
```bash
# Generate Go DDD project
project-gen new --lang go --name my-service --module example.com/my-service --port 8080 --out ./output/my-service

# Generate Python DDD project
project-gen new --lang python --name my-py-service --port 8000 --out ./output/my-py-service

# Generate K8s manifests
project-gen k8s --name my-service --port 8080 --replicas 3 --out ./output/k8s

# Validate DDD architecture
project-gen validate --path ./output/my-service --arch ddd
```
