# Toolchain versions

The scaffold centralizes versions so upgrades can be reviewed as an explicit change.

| Component | Version |
|---|---:|
| Java | 21 |
| Spring Boot | 4.1.0 |
| Gradle | 9.6.1 |
| Maven | 3.9.16 |
| Python | 3.13 |
| FastAPI | 0.139.2 |
| Go container | 1.26.5 |
| Next.js | 16.2.10 |
| React | 19.2.7 |
| Node container | 24 |
| PostgreSQL | 18.4 |

Production images should be pinned by digest. The local Compose file uses readable
version tags to keep the scaffold approachable.
