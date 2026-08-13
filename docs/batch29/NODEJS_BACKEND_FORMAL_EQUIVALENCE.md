# Node.js backend formal-equivalence boundary

## Language identity and route set

Node.js is represented by the independent source-language identifier
`javascript`. It is not an alias for `typescript`: TypeScript source is first
checked and compiled, while JavaScript source is executed directly by the
pinned Node.js runtime. Evidence from one language therefore cannot satisfy a
route owned by the other.

The `javascript-node26-completion-18` route set contains both directions
between JavaScript and each existing backend language:

- Java, C#, Go, Rust, Python, TypeScript, C++, Objective-C, and Swift;
- exactly 18 directed routes; and
- no same-language route or implicit reverse-direction credit.

Together with the existing nine-language matrix, this produces the explicit
`ten-language-complete-90` matrix.

## Exact local profile

The JavaScript side is restricted to Node.js 26.0.0, ES2022 ESM source, and
synchronous typed-pure functions/modules. Every parameter and return value must
have an unambiguous JSDoc declaration in the canonical type system:
`integer`, finite `number`, `boolean`, or `string`. Missing, duplicate,
conflicting, union, nullable, `any`, `unknown`, object, array, BigInt, Promise,
or inferred-only declarations fail closed.

The JavaScript analyzer records concrete UTF-8 byte spans and syntax chunks.
The emitter preserves the canonical rules with explicit guards where the Node
number model is narrower than the canonical integer model:

- integer inputs and results must remain `Number.isSafeInteger` values;
- division and remainder by zero are errors;
- integer division truncates toward zero;
- equality is emitted as strict `===`/`!==`;
- non-finite numbers and values outside the declared no-error domain are
  rejected; and
- string equality and concatenation use JavaScript value semantics only inside
  the declared string profile.

Route evidence binds source and target syntax spans, normalized semantic IR,
phrase/chunk topology, per-function behavior cases, module composition, helper
source digests, toolchain identity, and replay commands. SMT results apply only
to the normalized bounded IR and its recorded assumptions; they are not a
proof of the Node.js runtime or compiler implementation.

## Explicitly unsupported semantics

The local profile rejects CommonJS, dynamic import, top-level side effects,
async functions, generators, Promise/timer/event-loop behavior, `this`,
prototype mutation, classes/methods, getters/setters, Buffer/stream/process
state, filesystem/network access, package resolution and lifecycle scripts,
native addons, reflection/eval, and framework behavior. These require separate
runtime or framework evidence and remain `NOT_RUN` here.

## Evidence status

Only the Batch 29 route validator and route gate may derive each direction's
local result. A successful local run remains `limited / NOT_CERTIFIED`.
Compiler/runtime semantic soundness, independent holdout execution, customer
repositories, production operation, and external certification remain
`NOT_RUN` until their distinct authorized gates are executed.

The governed commands are:

```sh
make -f Makefile.batch29 b29-nodejs-prepare
make -f Makefile.batch29 b29-nodejs-replay
python3 scripts/operations/validate_translation_route_matrix.py
```

Each generated route must also pass its own `validate_route.py` and
`run_route_gate.py` invocation; a pass in one direction never upgrades its
reverse direction.
