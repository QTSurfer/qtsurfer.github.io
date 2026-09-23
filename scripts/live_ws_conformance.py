# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=13", "httpx>=0.27", "jsonschema>=4.23", "pyyaml>=6"]
# ///
"""Check asyncapi.yaml against itself and against the running service.

    uv run scripts/live_ws_conformance.py --examples
        Offline. Validates every message example in asyncapi.yaml against that message's payload
        schema (schemas referenced from openapi.yaml included). No network, no credentials.

    QTSURFER_APIKEY=... uv run scripts/live_ws_conformance.py [--run-id RUN_ID]
        Live. Mints a token through the REST API, opens the WebSocket, and validates every frame the
        server sends against the schema the spec says it must match: connect, a refused subscribe,
        live.params on a run that does not exist, refresh, and a server ping answered with a pong.
        With --run-id (a run you own, or a public one, that relays), also waits for one signal push
        and validates it.

Exits non-zero on the first frame that does not match.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from pathlib import Path

import httpx
import jsonschema
import websockets
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API = "https://api.qtsurfer.net/v1"


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())


DOCS: dict[str, dict] = {}


def deref(node, doc: str):
    """Inline every $ref, local ('#/...') or into a sibling file ('./openapi.yaml#/...')."""
    if isinstance(node, list):
        return [deref(item, doc) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        target_doc, _, pointer = ref.partition("#")
        target_doc = target_doc.removeprefix("./") or doc
        if target_doc not in DOCS:
            DOCS[target_doc] = load(target_doc)
        target = DOCS[target_doc]
        for part in filter(None, pointer.split("/")):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return deref(copy.deepcopy(target), target_doc)
    return {key: deref(value, doc) for key, value in node.items()}


def messages() -> dict[str, dict]:
    DOCS["asyncapi.yaml"] = load("asyncapi.yaml")
    return deref(DOCS["asyncapi.yaml"]["components"]["messages"], "asyncapi.yaml")


def check(frame: dict, message: str, catalogue: dict[str, dict]) -> None:
    try:
        jsonschema.validate(frame, catalogue[message]["payload"])
    except jsonschema.ValidationError as e:
        sys.exit(f"FAIL {message}: {e.message}\n  frame: {json.dumps(frame)[:400]}")
    print(f"ok   {message}: {json.dumps(frame)[:140]}")


def check_examples() -> None:
    catalogue = messages()
    count = 0
    for name, message in catalogue.items():
        for example in message.get("examples", []):
            check(example["payload"], name, catalogue)
            count += 1
    print(f"{count} examples match their schemas")


class Connection:
    """Reads frames, splitting a WebSocket message into one JSON object per line."""

    def __init__(self, ws):
        self.ws = ws
        self.pending: list[dict] = []

    async def next(self, timeout: float) -> dict:
        while not self.pending:
            raw = await asyncio.wait_for(self.ws.recv(), timeout)
            self.pending.extend(json.loads(line) for line in raw.splitlines() if line.strip())
        return self.pending.pop(0)

    async def reply(self, command_id: int, timeout: float = 10) -> dict:
        """The reply to one command, answering any ping that arrives first."""
        while True:
            frame = await self.next(timeout)
            if frame == {}:
                await self.ws.send("{}")
                continue
            if frame.get("id") == command_id:
                return frame


async def live(api: str, run_id: str | None, push_timeout: float) -> None:
    catalogue = messages()
    server = DOCS["asyncapi.yaml"]["servers"]["staging"]
    url = f"{server['protocol']}://{server['host']}{DOCS['asyncapi.yaml']['channels']['connection']['address']}"
    key = os.environ.get("QTSURFER_APIKEY")
    if not key:
        sys.exit("QTSURFER_APIKEY is not set (or pass --examples for the offline check)")

    def mint(client: httpx.Client, jwt: str) -> str:
        response = client.post(f"{api}/live/token", headers={"Authorization": f"Bearer {jwt}"})
        response.raise_for_status()
        return response.json()["token"]

    with httpx.Client(timeout=20) as client:
        auth = client.post(f"{api}/auth/token", headers={"X-API-Key": key})
        auth.raise_for_status()
        jwt = auth.json()["access_token"]
        token, fresh_token = mint(client, jwt), mint(client, jwt)

    print(f"connecting to {url}")
    async with websockets.connect(url) as ws:
        conn = Connection(ws)

        await ws.send(json.dumps({"id": 1, "connect": {"token": token}}))
        connected = await conn.reply(1)
        check(connected, "ConnectReply", catalogue)
        ping_every = connected["connect"].get("ping", 25)

        await ws.send(json.dumps({"id": 2, "subscribe": {"channel": "sig:conformanceCheckNoSuchRun"}}))
        refused = await conn.reply(2)
        check(refused, "ErrorReply", catalogue)
        if refused["error"]["code"] != 103:
            sys.exit(f"FAIL subscribe to a run that is not yours: expected code 103, got {refused}")

        await ws.send(json.dumps({"id": 3, "rpc": {"method": "live.params", "data": {
            "runId": "conformanceCheckNoSuchRun", "params": {"anything": "1"}}}}))
        missing = await conn.reply(3)
        check(missing, "ErrorReply", catalogue)
        if missing["error"]["code"] != 404:
            sys.exit(f"FAIL live.params on a run that does not exist: expected code 404, got {missing}")

        await ws.send(json.dumps({"id": 4, "refresh": {"token": fresh_token}}))
        check(await conn.reply(4), "RefreshReply", catalogue)

        if run_id:
            await ws.send(json.dumps({"id": 5, "subscribe": {"channel": f"sig:{run_id}"}}))
            check(await conn.reply(5), "SubscribeReply", catalogue)
            print(f"waiting up to {push_timeout:.0f}s for a signal on sig:{run_id}")
            while True:
                frame = await conn.next(push_timeout)
                if frame == {}:
                    await ws.send("{}")
                    continue
                if "push" in frame and "pub" in frame["push"]:
                    check(frame, "SignalPush", catalogue)
                    break

        print(f"waiting up to {ping_every * 2}s for a server ping")
        while True:
            frame = await conn.next(ping_every * 2)
            if frame == {}:
                check(frame, "Ping", catalogue)
                await ws.send("{}")
                break
    print("the running service matches asyncapi.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--examples", action="store_true", help="offline: check the spec's own examples only")
    parser.add_argument("--api", default=os.environ.get("QTSURFER_API", DEFAULT_API))
    parser.add_argument("--run-id", help="also wait for, and check, one signal push from this run")
    parser.add_argument("--push-timeout", type=float, default=120)
    args = parser.parse_args()
    if args.examples:
        check_examples()
    else:
        asyncio.run(live(args.api, args.run_id, args.push_timeout))


if __name__ == "__main__":
    main()
