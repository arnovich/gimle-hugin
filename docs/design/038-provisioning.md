# Task 038: local swarm provisioning

This increment turns the transport experiment's generated identities into
operator-created, restart-safe local state. It does not start a daemon, board,
runner, or cloud resources. Commands produce only local files; automation can
deliver an invite and bootstrap contacts to each private host.

## Plan

1. Replace the provisional pyOpenSSL dependency with a verifier for this
   fixed three-certificate private hierarchy. Use cryptography's documented
   direct issuer-signature check, enforce the complete root/intermediate/leaf
   profile explicitly, and retain OpenSSL's independent path validation at
   the real TLS handshake. Validate the pinned root's self-signature, CA
   flag/path length one, signing key usage and validity; the root-signed
   intermediate's CA flag/path length zero, signing key usage and validity;
   the leaf's non-CA flag, digital-signature usage, client/server EKUs,
   expected SAN derived from its SPKI, and validity. Require exact issuer
   relationships, Ed25519 keys, correct criticality and a closed extension
   allowlist. Test swapped/extra issuers, missing or malformed constraints,
   unknown critical extensions, expiry and signature failures.
2. Add `hugin swarm create`, `invite`, and `join` as lazy-loaded optional
   commands. `create` writes an offline root key, root certificate, initial
   signed policy, and public bootstrap bundle. `invite` writes a bounded
   reusable bearer file containing one scoped intermediate signing key,
   signed grant, public root/policy, and private-network seed hints.
3. `join` mints an independent node key and leaf certificate, validates the
   invite and signed policy, then writes owner-only persistent state. Explicit
   `--initialize-first` uses a matching bootstrap bundle to start an empty
   swarm. Ordinary join requires a reachable seed that serves a valid signed
   policy through root-pinned HTTPS. The seed hint is an IP and port; TLS
   validates its chain against the invite's pinned root, then the client
   verifies the leaf's SAN against the hash of its public key. Seed IPs must
   fall inside a narrowly configured private mesh CIDR. No redirects, proxy
   settings or ambient credentials are used. This online route is exercised
   against an isolated test listener; cross-host join waits for the daemon.
4. Persist the highest policy generation and reject rollback or same-generation
   forks on update. Reload checks file permissions, node-key/certificate
   match, grant scope, policy signature, and pinned root. Failed writes leave
   no apparently initialized state. Existing state is inspected, never
   replaced by a fresh identity on rerun. Node state contains its own key,
   public chain, grant, root, policy floor and seed hints, never the reusable
   invitation signing key. A refresh command signs a new policy generation;
   local install atomically raises the persisted floor. Secret-bearing output
   inside a Git worktree is refused, regardless of filename. Invite/root
   keys are never printed.
5. Add CLI and integration tests for first formation, two independent joins,
   restart stability, expired and swapped credentials, stale or unreachable
   seeds, policy rollback, symlinks/permissions, and crash cuts. Explicit
   invite scopes are required; no all-action default. Run the repo's
   required checks and panel review, then open a PR.

## Scope and dependency decision

The certificate profile here is intentionally closed: one pinned Ed25519 root,
one root-signed invitation CA with path length zero, and one Ed25519 TLS leaf.
The verifier does not attempt general Web PKI path building. The standard TLS
implementation validates live peers against the pinned root. The application
verifier checks the exact supplied three-certificate relationship and all
profile restrictions before accepting signed grant evidence. This removes
pyOpenSSL's pending-deprecation module from the runtime path. The established
cryptography path builder currently rejects Ed25519 keys with its Web PKI
algorithm policy, so it cannot be substituted for this hierarchy.

The CLI prepares local admission state. Peer registration, discovery, and
message replication are subsequent increments; an ordinary join's online
policy check establishes contact and a current authorization floor, but it
does not yet publish an agent advertisement. No cloud-ready join is claimed
until a supervised seed listener exists. A failed online join cannot fall
back to first-node initialization.

## Operator commands

Install the optional dependency set with `uv sync --extra swarm --group dev`.
The commands below use illustrative private-network addresses and directories
outside any Git checkout. Run them only with generated or privately delivered
credentials; never commit an admin directory, invite or node state.

```sh
hugin swarm create --name research --output /secure/hugin/research-admin
hugin swarm invite --admin /secure/hugin/research-admin \
  --scope research:read,post \
  --seed 10.42.0.10:7443 --seed 10.42.0.11:7443 \
  --output /secure/hugin/research.invite
hugin swarm join --invite-file /run/secrets/research.invite \
  --mesh-cidr 10.42.0.0/16 --state-dir /var/lib/hugin/swarm \
  --initialize-first \
  --bootstrap-bundle /run/secrets/research-bootstrap.json
hugin swarm status --state-dir /var/lib/hugin/swarm
```

Provisioning automation privately delivers `research.invite` to
`/run/secrets/research.invite` and copies the public
`/secure/hugin/research-admin/bootstrap.json` to
`/run/secrets/research-bootstrap.json` on the first host. Keep the admin
directory and its root key on the operator machine.

Use `--initialize-first` only for a new, empty swarm with the matching public
bootstrap bundle. Subsequent `join` commands omit that flag and bundle and
require an online seed serving `/v0/policy` over root-pinned HTTPS. The
current experiment server listens only on loopback, so this route is testable
locally but cannot yet join AWS/Hetzner hosts. The CLI reports `provisioned`
after writing state, since no daemon or agent advertisement exists yet.
Seed hints are numeric IP addresses with ports in this increment; DNS seeds
require checked resolution in the daemon increment. The mesh CIDR bounds all
seed connections, and an internet-wide CIDR is rejected.

An administrator refreshes policy with `hugin swarm policy-refresh --admin
/secure/hugin/research-admin`, then privately distributes the updated
`policy.json` and installs it with `hugin swarm policy-install --state-dir
/var/lib/hugin/swarm --policy-file /run/secrets/policy.json`. A node can renew
with `hugin swarm renew --state-dir /var/lib/hugin/swarm --invite-file
/run/secrets/replacement.invite`; the node ID remains stable while its leaf
and grant change. The initial grant lifetime is at most 30 days and policy
validity is seven days. Status reports expiry timestamps and current local
authorization health without secrets. Revocation lists are bounded to 512 IDs
per kind in the current signed-policy format; operators must rotate the root
before cumulative revocations exhaust that limit. Revocation retirement needs
expiry metadata in a later policy format.

Root and node private keys and invites are stored in files with mode 0600
inside mode 0700 directories. The reusable invitation signing key is never
copied into node state. All secret outputs inside Git worktrees are refused,
regardless of filename. A partial directory has no final `ready` marker and
cannot be loaded as initialized. Signed policy replacements use a synced
temporary file and atomic rename; rollback and same-generation forks fail.
Writable non-sticky ancestor directories are refused. Initialization publishes
a complete directory with one rename; if a process dies before publication,
an owner-only `.partial` sibling may remain and can be removed by the operator
after checking that the final directory exists. A persistent `.init.lock`
sibling coordinates concurrent initializers.

## Certificate decision

The [cryptography X.509 verifier](https://cryptography.io/en/latest/x509/verification/)
currently uses a Web PKI algorithm policy that rejects the Ed25519 chain
required by this private hierarchy. The prior experiment used
[pyOpenSSL's crypto module](https://www.pyopenssl.org/en/stable/api/crypto.html),
which its own documentation marks pending deprecation. This increment removes
that dependency. Its closed-profile check uses
[`verify_directly_issued_by`](https://cryptography.io/en/latest/x509/reference/)
to validate each issuer signature and name, and explicitly validates the
root/intermediate/leaf constraints listed above. That method alone does not
perform full X.509 path validation. During actual network communication,
Python's [TLS stack](https://docs.python.org/3/library/ssl.html) independently
validates the presented certificate chain against only the pinned swarm root;
the client then checks the leaf identity and profile. The test corpus includes
valid signatures on malformed certificates so profile checks cannot be
mistaken for mere signature verification.
