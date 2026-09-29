# Task 038 transport/admission experiment

This is the first implementation increment of the reviewed swarm design.
It is a local experiment, not a deployable swarm service or stable wire API.
The subsequent increments add persistent provisioning, a supervised daemon,
and discovery. No cloud account, real invite, private address or model key is
required to run this experiment.

## Plan

- Add an optional `swarm` dependency extra and an isolated swarm package.
- Generate an offline root, scoped invitation authority and independent node
  keys in temporary memory/files. Use maintained X.509 verification and JSON
  canonicalization implementations. Do not commit certificate/key fixtures.
- Prove actual HTTPS mutual authentication in separate local processes,
  binding the application grant and signed probe to the TLS peer certificate.
- Reject foreign swarms, expired credentials, swapped grants, revoked identities,
  missing certificates, wrong permissions, malformed and oversized input.
- Prove a stale client can fetch a signed policy without a client certificate,
  while the same connection cannot access the protected diagnostic endpoint.
- Keep diagnostic output to bounded result codes and counts. Suppress HTTP
  access logging; never emit credential objects, raw bodies or exception text.
- Review the implementation for security, protocol correctness and maintainability,
  then rework it in a fresh worktree as required by the repository guidelines.

## Scope boundary

Only loopback and ephemeral ports are used by the harness. These are test-only
transport choices, not exceptions in a production network policy. There is no
board replication, persistent enrollment, discovery, runner execution, cloud
provisioning or public listener. Policy generation floors are exercised in
memory; durable policy floors belong to the provisioning increment. Restart
safe identity, 100-peer discovery and seed-loss tests follow in later PRs.

The experiment uses real TLS and generated credentials, with no LLM calls.
Its failure tests are the gate for choosing dependencies and moving on to the
provisioning CLI. Never treat a passing probe as a production security review.

## Run the experiment

```sh
uv sync --extra swarm --group dev
uv run --extra swarm python -m gimle.hugin.swarm.experiment
uv run --extra swarm pytest tests/swarm -q -W error
```

The harness creates a fresh root and invite in memory, writes only the generated
node TLS material under an owner-only temporary directory, starts an independent
server process on loopback, and removes the files after the process exits. It
never reads cloud credentials, model credentials or existing swarm identities.
Its output contains result labels and package versions, not keys, certificates,
node IDs, ports, filesystem paths or raw exception messages. Early failures
report bounded stage codes. The internal child entry point is not a public CLI.

## Dependency experiment results

Pinned optional dependencies are aiohttp 3.14.3, HTTPX 0.28.1, cryptography
50.0.1, pyOpenSSL 26.4.0 and rfc8785 0.1.4. HTTPX already exists transitively
through the model SDKs; declaring it here makes the experiment reproducible.
All are optional: importing normal Hugin functionality does not import them.
CI already installs all extras, so the transport tests run in its normal suite.
Tests skip when the optional extra is absent in a local installation.

The tested cryptography certificate-path verifier rejected Ed25519 certificate
keys with `Forbidden public key algorithm`. Certificate issuance and signatures
work, and OpenSSL accepts the chain. The experiment therefore uses OpenSSL's
strict store verification through one isolated `verify_chain` adapter. It does
not replace path validation with handwritten signature checks.

This is a **provisional experiment dependency**, not completion of the production
dependency gate: pyOpenSSL's crypto module is marked pending deprecation. Before
building production enrollment, review its supported lifecycle or choose another
maintained verifier that passes these same Ed25519/profile tests. A passing TLS
probe alone cannot settle that maintenance decision.
[pyOpenSSL certificate verification](https://www.pyopenssl.org/en/stable/api/crypto.html),
[cryptography verification API](https://cryptography.io/en/latest/x509/verification/).

HTTPX's documented SNI and network-stream extensions let the client connect to
an explicit loopback IP while retaining hostname validation and inspecting the
actual TLS certificate. Full node hashes are split into two DNS labels to stay
within DNS label limits. Both public node evidence and permission grants are
bound to that TLS identity.
[HTTPX extensions](https://www.python-httpx.org/advanced/extensions/).

Canonical signatures use rfc8785, with additional experiment bounds: 64 KiB
records, depth eight, integer-only numbers, duplicate-key rejection and exact
canonical wire representation. The experiment protocol is explicitly version 0;
it is not the production message schema.
[rfc8785 project](https://pypi.org/project/rfc8785/).

## Review and refinements

An initial implementation was reviewed independently for security/publication,
protocol/test correctness and staff-level maintainability. The improved version
was rebuilt in a fresh worktree with distinct credential construction, admission,
temporary material, transport and harness modules. The bounded canonical-wire
primitive and regression tests were retained.

| Finding | Resolution |
| --- | --- |
| Revocation test opened a fresh TLS connection | Reuse one actual keepalive connection and assert the same stream across node revocation, grant revocation and policy expiry |
| Foreign-peer test could fail on the wrong side | Trust the legitimate server root while presenting a foreign client chain; server admission must reject it |
| HTTP parser errors reflected raw malformed headers | Isolated redacted protocol handler and logger; raw-TLS canary test checks both response and captured logs |
| Verifier lifecycle was undocumented | Single OpenSSL adapter, exact versions, reproduced Ed25519 incompatibility and explicit production dependency gate |
| Child startup/exit failures were opaque | Bounded stage codes, terminate/kill exit-race handling and caller-failure cleanup regression |
| Trusted decisions used mutable dictionaries | Immutable validated policy snapshot and permission sets; public records returned as independent copies |

The HTTP error adapter uses aiohttp's pinned RequestHandler interface. Its
malformed-header regression test is required for upgrades. Eight concurrent
HTTP handlers and bounded bodies/timeouts limit application work; this does
**not** establish a limit on open sockets or pre-authentication TLS handshakes.
Those are required daemon-stage gates. Loopback binding is hardcoded here.

Certificate files are generated at runtime, not committed fixtures. Ignore
rules cover common key/invite files and local cloud/environment state. Exact
staged files and the outgoing diff must still be checked: ignore rules do not
protect files already tracked or explicitly force-added.


## Follow-up verdict

All three independent judges approved the revised loopback experiment with no
remaining blocking findings. Security and protocol reviewers each independently
ran the 33-test suite with warnings treated as errors. The staff reviewer
approved the revised structure and explicit dependency/production boundaries.
The full repository validation results are recorded in the PR.

No real cloud/model credentials or deployment addresses were used. The staged
addition was checked for generated private keys, credential filenames, cloud
key patterns, local home paths and unexpected URL hosts before publication.
This supplements the repository's secret-detection hook and explicit staging.

A subsequent full-suite run exposed a short child-startup deadline under load.
Startup now has a separate bounded 30-second allowance; network deadlines are
unchanged. A deterministic silent-readiness-pipe test verifies the redacted
startup failure and process cleanup, bringing the local strict suite to 34 tests.
