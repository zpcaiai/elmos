# SOTA Cache Algorithm Matrix and Primary Sources

This matrix is a research input, not a claim that one policy will be best for ELMOS. Final selection requires equal-capacity replay on ELMOS traces.

| Algorithm / framework | Core idea | ELMOS use | Deployment status |
|---|---|---|---|
| SIEVE (NSDI 2024) | FIFO-like queue plus visited bit; hits avoid list reordering | High-concurrency local object/action cache; scan-resistant fallback | Production candidate |
| S3-FIFO (SOSP 2023) | Small FIFO filters one-hit objects; main FIFO and ghost queue retain reusable objects | Local CAS and one-hit-heavy conversion/build traces | Production candidate |
| TinyLFU / W-TinyLFU | Approximate frequency admission with recency window | L0 metadata and mixed recency/frequency workloads | Production candidate |
| Size-aware TinyLFU | Frequency/value admission adjusted for object size | Remote CAS with heterogeneous AST/IR/build artifacts | Production candidate |
| GDSF | Frequency × retrieval/recompute cost ÷ size plus inflation | Expensive model/compiler/test artifacts | Production candidate |
| 3L-Cache (FAST 2025) | Low-overhead learning-based eviction and auto-tuning | Shadow/simulator comparison for large heterogeneous caches | Experimental |
| Merlin (OSDI 2026) | Fine-grained pattern characterization for adaptive eviction | Candidate adaptive expert after independent reproduction | Experimental |
| LAH / S4-FIFO (OSDI 2026) | Learn bounded parameters of a simple FIFO heuristic off the data path | Preferred learning-augmented control-plane pattern | Experimental-to-canary |
| SCION (2026 preprint) | Tiny off-path fingerprint selects among strong policy experts | Design reference for policy orchestration | Research input |
| DAG next-use / Belady-inspired | Use known future consumer order rather than only access history | Active conversion DAG protection, prefetch, placement, restore bypass | ELMOS-specific production candidate |

## Primary sources

1. Yazhuo Zhang et al., “SIEVE is Simpler than LRU: an Efficient Turn-Key Eviction Algorithm for Web Caches,” NSDI 2024. https://www.usenix.org/conference/nsdi24/presentation/zhang-yazhuo
2. Juncheng Yang et al., “FIFO Queues are All You Need for Cache Eviction,” SOSP 2023. Official artifact: https://github.com/Thesys-lab/sosp23-s3fifo
3. Gil Einziger, Roy Friedman, and Ben Manes, “TinyLFU: A Highly Efficient Cache Admission Policy.” https://arxiv.org/abs/1512.00727
4. Gil Einziger et al., “Lightweight Robust Size Aware Cache Management.” https://arxiv.org/abs/2105.08770
5. Wenbin Zhou et al., “3L-Cache: Low Overhead and Precise Learning-based Eviction Policy for Caches,” FAST 2025. https://www.usenix.org/conference/fast25/presentation/zhou-wenbin
6. Liujia Li et al., “Merlin: An Efficient Adaptive Cache Eviction Algorithm via Fine-Grained Characterization,” OSDI 2026. https://www.usenix.org/conference/osdi26/technical-sessions
7. Haocheng Xia et al., “Learning-Augmented Heuristics: Simple Yet Smart, Robust and Interpretable Cache Eviction,” OSDI 2026. https://www.usenix.org/conference/osdi26/technical-sessions
8. Qizhi Wang, “SCION: Size-aware Policy Orchestration for Nonstationary Object Caches,” 2026 preprint. https://arxiv.org/abs/2605.01055
9. Bazel documentation, “Remote Caching,” for the Action Cache plus CAS separation. https://bazel.build/remote/caching
10. libCacheSim official repository for reproducible multi-policy trace simulation. https://github.com/1a1a11a/libCacheSim

## Interpretation rules

- Conference and paper results apply to their reported traces and objectives, not automatically to ELMOS.
- New learning-based policies remain disabled for production write decisions until ELMOS-specific replay, shadow, and canary gates pass.
- Simple fixed policies remain mandatory baselines because learned overhead and workload mismatch can erase theoretical gains.
- ELMOS must optimize avoided work and critical path, not only the object miss ratio used by many object-cache papers.
