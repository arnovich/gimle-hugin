"""Optional local provisioning commands for private Hugin swarms."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def add_swarm_commands(parser: argparse.ArgumentParser) -> None:
    """Register only local file operations; runtime imports stay optional."""
    commands = parser.add_subparsers(dest="swarm_action", required=True)
    create = commands.add_parser(
        "create", help="Create an offline swarm authority"
    )
    create.add_argument("--name", required=True)
    create.add_argument("--output", type=Path, required=True)
    invite = commands.add_parser("invite", help="Issue a scoped bearer invite")
    invite.add_argument("--admin", type=Path, required=True)
    invite.add_argument(
        "--scope", action="append", required=True, metavar="GROUP:READ,POST"
    )
    invite.add_argument(
        "--seed", action="append", default=[], metavar="IP:PORT"
    )
    invite.add_argument("--output", type=Path, required=True)
    join = commands.add_parser(
        "join", help="Prepare a persistent node identity"
    )
    join.add_argument("--invite-file", type=Path, required=True)
    join.add_argument("--state-dir", type=Path, required=True)
    join.add_argument("--mesh-cidr", required=True)
    join.add_argument("--initialize-first", action="store_true")
    join.add_argument("--bootstrap-bundle", type=Path)
    renew = commands.add_parser(
        "renew", help="Renew one node without changing its identity"
    )
    renew.add_argument("--state-dir", type=Path, required=True)
    renew.add_argument("--invite-file", type=Path, required=True)
    refresh = commands.add_parser(
        "policy-refresh", help="Sign the next policy snapshot"
    )
    refresh.add_argument("--admin", type=Path, required=True)
    refresh.add_argument("--revoke-node", action="append", default=[])
    refresh.add_argument("--revoke-grant", action="append", default=[])
    install = commands.add_parser(
        "policy-install", help="Raise a node's policy floor"
    )
    install.add_argument("--state-dir", type=Path, required=True)
    install.add_argument("--policy-file", type=Path, required=True)
    status = commands.add_parser(
        "status", help="Show safe local identity status"
    )
    status.add_argument("--state-dir", type=Path, required=True)


def _scopes(values: list[str]) -> dict[str, list[str]]:
    """Parse explicit group permissions without an implicit broad default."""
    from gimle.hugin.swarm._provision_io import ProvisionError

    result: dict[str, list[str]] = {}
    for value in values:
        group, separator, actions = value.partition(":")
        if not separator or group in result:
            raise ProvisionError("invalid_scope")
        result[group] = actions.split(",")
    return result


def cmd_swarm(args: argparse.Namespace) -> int:
    """Execute one local provisioning action with bounded diagnostics."""
    try:
        from gimle.hugin.swarm._provision_io import ProvisionError
        from gimle.hugin.swarm.admission import _permissions, verify_credential
        from gimle.hugin.swarm.provisioning import (
            create_admin,
            install_policy,
            issue_invite,
            join_swarm,
            load_node_state,
            refresh_policy,
            renew_node,
        )
        from gimle.hugin.swarm.wire import ProtocolError

        now = datetime.now(timezone.utc).replace(microsecond=0)
        if args.swarm_action == "create":
            result = {
                "status": "created",
                "swarm_id": create_admin(args.name, args.output, now),
            }
        elif args.swarm_action == "invite":
            result = {
                "status": "issued",
                "grant_id": issue_invite(
                    args.admin, _scopes(args.scope), args.seed, args.output, now
                ),
            }
        elif args.swarm_action == "join":
            state = asyncio.run(
                join_swarm(
                    args.invite_file,
                    args.state_dir,
                    args.mesh_cidr,
                    now,
                    initialize_first=args.initialize_first,
                    bootstrap_path=args.bootstrap_bundle,
                )
            )
            result = {"status": "provisioned", "node_id": state.node.node_id}
        elif args.swarm_action == "policy-refresh":
            policy = refresh_policy(
                args.admin,
                now,
                revoked_nodes=args.revoke_node,
                revoked_grants=args.revoke_grant,
            )
            result = {
                "status": "refreshed",
                "generation": policy["payload"]["generation"],
            }
        elif args.swarm_action == "renew":
            state = renew_node(args.state_dir, args.invite_file, now)
            result = {"status": "renewed", "node_id": state.node.node_id}
        elif args.swarm_action == "policy-install":
            install_policy(args.state_dir, args.policy_file, now)
            result = {"status": "installed"}
        else:
            state = load_node_state(args.state_dir, now)
            authorization = "inactive"
            try:
                grant = state.node.credential()["grant"]["payload"]
                group, action = sorted(_permissions(grant["groups"]))[0]
                verify_credential(
                    state.node.credential(),
                    state.node.der,
                    state.node.root,
                    state.policy,
                    now,
                    group,
                    action,
                )
                authorization = "active"
            except (ProvisionError, ProtocolError):
                pass
            result = {
                "status": "loaded",
                "local_authorization": authorization,
                "node_id": state.node.node_id,
                "swarm_id": state.policy["payload"]["swarm_id"],
                "policy_expires_at": state.policy["payload"]["expires_at"],
                "grant_expires_at": state.node.credential()["grant"]["payload"][
                    "expires_at"
                ],
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except ImportError as error:
        if error.name not in {"cryptography", "httpx", "rfc8785"}:
            raise
        print("swarm extra is required", file=sys.stderr)
        return 2
    except (ProvisionError, ProtocolError) as error:
        print(f"swarm error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print("swarm error: invalid_local_state", file=sys.stderr)
        return 2
