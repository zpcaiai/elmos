# Node toolchain pin drift — every TypeScript/JavaScript target route fails closed

> 2026-08-18, Claude Code. Root cause is confirmed, reversible, and the gate
> behaved correctly. The decision at the end is the engine owner's, not an agent's.

## Symptom

The 222-node matrix was launched at 2026-08-18T08:13:44Z on `a2f6f6577`
(11 languages, 110 directed routes). It was stopped at node 20 with 4 failures
and no summary line; its log is retained as
`.ai/matrix222-run-VOID-stopped-early.log` and is **VOID**.

```
....FF........FF....
    ↑↑        ↑↑
    5,6       15,16
```

| # | route | verdict |
| --- | --- | --- |
| 5 | java → **typescript** | FAILED |
| 6 | java → **javascript** | FAILED |
| 15 | python → **typescript** | FAILED |
| 16 | python → **javascript** | FAILED |

Every other target (csharp, go, rust, cpp, objc, swift, php, java, python)
passed. The discriminator is the **target being Node-hosted**, not PHP.

## Cause chain

```
pipeline.py:847   RouteError: PIPELINE_NO_VERIFIED_UNITS   (0 of 3 units passed)
batch-report.json status_counts {"FAILED": 3}
                  WU-00001..3 reason = EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH
toolchains.py:2424 raised by _verify_node_topology_identity()
```

`_discover_node_topology()` walks the Mach-O dependency closure of the pinned
Node executable with `otool` and hashes it. The result is compared against four
constants pinned in source:

```python
_EXPECTED_NODE_CLOSURE_COMPONENT_COUNT = 25
_EXPECTED_NODE_CLOSURE_EDGE_COUNT      = 49
_EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT = 43
_EXPECTED_NODE_TOPOLOGY_SHA256 = 2a77ac1d4bcf11286a97e403060b6a6490d21127857b6d1ba21806f026451bfd
```

Those constants were last written in `badffaba5` — the commit the **182/182**
matrix ran green on. Node itself has not changed: `v26.0.0`, binary mtime
2026-05-22 12:20.

What changed is one of Node's dependencies:

```
otool -L .../node  →  /opt/homebrew/opt/sqlite/lib/libsqlite3.dylib   (direct dependency)

/opt/homebrew/Cellar/sqlite/3.53.3   Jul  3 15:19     <- what the pin was taken against
/opt/homebrew/Cellar/sqlite/3.53.4   Aug 18 12:58     <- current, /opt/homebrew/opt/sqlite -> here
```

The 3.53.4 install receipt says `installed_on_request: false` and carries
timestamp `1787029127` — **the identical timestamp** as the `php 8.5.9` receipt,
which says `installed_on_request: true`.

**Installing PHP for the eleventh language pulled a `sqlite` upgrade as a
dependency; that changed Node's dylib closure; that broke the pinned Node
toolchain identity; that fails every Node-hosted target route closed.**

## This is the gate working, not a bug

The engine refused to produce route evidence against a toolchain that no longer
matches its pin. That is the fail-closed contract. Nothing here should be
"fixed" by relaxing the check.

## The decision (owner's, not an agent's)

Both paths are available; `3.53.3` is still on disk, so nothing is lost either way.

**A — restore the pinned environment.** Relink `sqlite` 3.53.3 so Node's closure
returns to the identity the pin was taken against. Keeps the 182/182 evidence
and the new 222 run directly comparable, and requires no source change. Must
confirm PHP 8.5.9 still probes green afterwards — PHP's own pins cover its own
Cellar tree, so it is expected to be unaffected, but that has not been executed.

**B — re-pin Node to the new closure.** Accepts sqlite 3.53.4 into the certified
toolchain identity and rewrites the four constants. Note there is **no node
pinning tool in `tools/`** — only `pin_php_toolchain.py` — so the four values
would have to be derived by hand from `_node_topology_identity()`. This changes
what the certified toolchain *is*, so every earlier Node-route result was
produced against a different toolchain than every later one.

Until one is chosen, the 222-node matrix cannot produce a clean run: 40 of its
220 route nodes (10 sources x {typescript, javascript} x {SMALL, MEDIUM}) will
fail closed.

## Also worth knowing

Disk is at **18 GB free / 99% used**. The 182-node run consumed ~22 GB net. A
222-node run will not fit in the current headroom even once the pin is settled;
plan reclamation before relaunching. Nothing safely regenerable remains —
Xcode DerivedData is already 0 and `~/.cache/codex-runtimes` (1.5 GB) is the
offline toolchain the matrix depends on.

---

## RESOLVED 2026-08-18 — option A applied and verified

`sqlite` is keg-only and is **not** linked into `/opt/homebrew/lib`; Node reaches
it only through `/opt/homebrew/opt/sqlite`. So the restoration is one symlink:

```sh
ln -sfn ../Cellar/sqlite/3.53.3 /opt/homebrew/opt/sqlite
```

Original target recorded in `/tmp/sqlite-link-original.txt`
(`../Cellar/sqlite/3.53.4`); 3.53.4 remains on disk, so this is reversible.

Verification, on current source:

```text
PINNED : sha=2a77ac1d4bcf11286a97e403060b6a6490d21127857b6d1ba21806f026451bfd comp=25 edge=49 sys=43
ACTUAL : sha=2a77ac1d4bcf11286a97e403060b6a6490d21127857b6d1ba21806f026451bfd comp=25 edge=49 sys=43
VERIFY : PASS — node topology matches the pin
```

All four fields identical to the values pinned in `badffaba5`. Route-level
confirmation: `java-typescript`, `java-javascript`, `python-typescript` and
`java-php` all **PASS** (they were the failing kinds before). `node -v` is
unchanged and `node:sqlite` still loads. PHP 8.5.9 also links
`opt/sqlite/lib/libsqlite3.dylib`, and still reports its pinned version string
after the revert — PHP's pins cover its own Cellar tree, which is unaffected.

**No source change was required and none was made for this.**

## Separate, pre-existing blocker found while verifying: PHP as a *source*

20 of the 222 nodes cannot pass, for a reason unrelated to the toolchain pin:

```text
discovery: MODULE_INVENTORY_UNSUPPORTED:php
           "add.php compiler-backed module enumeration did not run"
verdict:   NOT_RUN  ->  batch status_counts {"SKIPPED_NOT_READY": 3}
           ->  pipeline.py:847 PIPELINE_NO_VERIFIED_UNITS
```

Confirmed uniform across `php-java`, `php-javascript`, `php-python`, `php-go`,
`php-rust`, `php-swift`; each fails in ~1.4 s without touching a toolchain, so
these cost no disk and no time.

```
php-as-source nodes in the matrix   20   ALL FAIL (structural)
php-as-target nodes in the matrix   20   java-php verified PASS
```

PHP participates in `typed-pure-function-v1` only; repository-scale discovery
needs compiler-backed module enumeration, which PHP does not have. The author of
`a2f6f6577` stated it plainly: *"Every one of the 110 directions is NOT_RUN."*
This is that in-flight scope, not a regression and not something to work around.

**Ceiling until PHP module inventory lands: 202/222.**

## Remaining blocker: disk

```
Data volume   16 GB free, 99% used
182-node run consumed ~22 GB net
```

Nothing reclaimable is left under this agent's authority. The whole repository is
2.9 GB; its regenerable build output totals ~220 MB. Xcode DerivedData is already
0, and `~/.cache/codex-runtimes` (1.5 GB) is the offline toolchain the matrix
depends on. This agent's own pytest debris was removed and freed nothing
measurable. The 941 GB in use is user data; choosing what goes is the owner's
call.

A 222-node (or 202-node) run launched at 16 GB free will wall before finishing
and produce another VOID log. Do not relaunch until headroom is restored.
