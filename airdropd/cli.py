from __future__ import annotations

import argparse
import logging
import socket
import sys
from pathlib import Path

from airdropd import __version__
from airdropd import config as cfgmod
from airdropd import discovery, identity
from airdropd.daemon import run_receiver
from airdropd.localsend import DEVICE_MODEL, DEVICE_TYPE

log = logging.getLogger("airdrop")


def _apply_overrides(cfg, args):
    if args.port is not None:
        cfg.port = args.port
    if args.protocol is not None:
        cfg.protocol = args.protocol
    return cfg


def _fingerprint(cfg, override_dir) -> str:
    cert_dir = cfgmod.config_dir(override_dir)
    cert = cert_dir / "cert.pem"
    if cert.is_file():
        try:
            return identity.fingerprint(cert)
        except Exception:
            return "unreadable-cert"
    return "not-generated"


def cmd_peers(args) -> int:
    cfg = _apply_overrides(cfgmod.load(args.config_dir), args)
    cert_dir = cfgmod.config_dir(args.config_dir)
    cert = cert_dir / "cert.pem"
    fp = identity.fingerprint(cert) if cert.is_file() else "http-no-tls"
    from airdropd.daemon import make_announce

    rows: list[tuple[str, str, str, str]] = []
    if not args.airdrop:
        peers = discovery.discover(make_announce(cfg, fp), timeout=args.timeout)
        rows += [(p.alias, p.ip, p.protocol, p.device_model) for p in peers]
    if args.airdrop:
        from airdropd import awdl

        try:
            rows += [
                (p.name or p.peer_id, p.address, "airdrop", "")
                for p in awdl.discover_peers(iface=args.iface or _awdl_iface())
            ]
        except awdl.AwdlError as exc:
            print(f"airdrop: {exc}", file=sys.stderr)
    if not rows:
        print("no peers found")
        return 0
    print(f"{'ALIAS':<24} {'ADDRESS':<30} PROTO  MODEL")
    for alias, address, proto, model in sorted(rows, key=lambda r: r[0].lower()):
        print(f"{alias:<24} {address:<30} {proto:<6} {model}")
    return 0


def _awdl_iface() -> str | None:
    from airdropd import awdl

    return awdl.find_awdl_iface()


def cmd_send(args) -> int:
    cfg = _apply_overrides(cfgmod.load(args.config_dir), args)
    paths = [Path(p).expanduser().resolve() for p in args.files]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print(f"error: not a file: {', '.join(str(m) for m in missing)}", file=sys.stderr)
        return 1
    if args.airdrop:
        return _send_airdrop(args, paths)
    cert_dir = cfgmod.config_dir(args.config_dir)
    cert = cert_dir / "cert.pem"
    fp = identity.fingerprint(cert) if cert.is_file() else "http-no-tls"
    from airdropd.localsend import DeviceInfo
    from airdropd.daemon import make_announce
    from airdropd import sender

    peers = discovery.discover(make_announce(cfg, fp), timeout=args.timeout)
    if args.to:
        needle = args.to.lower()
        peers = [p for p in peers
                 if needle in p.alias.lower() or needle in p.fingerprint.lower()]
        if not peers:
            print(f"error: no peer matches {args.to!r}", file=sys.stderr)
            return 1
    if not peers:
        iface = _awdl_iface()
        hint = " (AWDL interface present — try --airdrop)" if iface else ""
        print(f"error: no peers found{hint}", file=sys.stderr)
        return 1
    if len(peers) > 1:
        if not sys.stdin.isatty():
            print("error: multiple peers, use --to:", file=sys.stderr)
            for p in peers:
                print(f"  {p.alias} ({p.ip})", file=sys.stderr)
            return 1
        for i, p in enumerate(peers, 1):
            print(f"  {i}. {p.alias} ({p.ip})")
        choice = input("Send to: ").strip()
        try:
            peers = [peers[int(choice) - 1]]
        except (ValueError, IndexError):
            print("error: invalid choice", file=sys.stderr)
            return 1
    peer = peers[0]
    sender_info = DeviceInfo(alias=cfg.alias, fingerprint=fp,
                             device_model=DEVICE_MODEL, device_type=DEVICE_TYPE)
    log.info("sending %d file(s) to %s (%s)", len(paths), peer.alias, peer.ip)
    try:
        def progress(name, pct):
            log.info("%s: %d%%", name, pct)

        sender.send_files(peer, sender_info, paths, progress_log=progress)
    except sender.SendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    log.info("done")
    return 0


def _send_airdrop(args, paths: list[Path]) -> int:
    from airdropd import awdl

    iface = args.iface or _awdl_iface()
    if iface is None:
        print("error: no AWDL interface found (is the owl service running?)", file=sys.stderr)
        return 1
    if not paths:
        print("error: no files", file=sys.stderr)
        return 1
    try:
        if args.to:
            receiver = args.to
        else:
            peers = awdl.discover_peers(iface=iface)
            if not peers:
                print("error: no AirDrop receivers found", file=sys.stderr)
                return 1
            for p in peers:
                print(f"  {p.index}. {p.name or p.peer_id} ({p.address})")
            if not sys.stdin.isatty():
                print("error: multiple receivers, use --to <index-or-id>", file=sys.stderr)
                return 1
            choice = input("Send to: ").strip()
            try:
                receiver = str(peers[int(choice)].index)
            except (ValueError, IndexError):
                print("error: invalid choice", file=sys.stderr)
                return 1
        log.info("sending via AirDrop on %s", iface)
        for p in paths:
            awdl.send_native(p, receiver, iface=iface)
    except awdl.AwdlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    log.info("done")
    return 0


def cmd_receive(args) -> int:
    if args.airdrop:
        from airdropd import awdl

        iface = args.iface or _awdl_iface()
        if iface is None:
            print("error: no AWDL interface found (is the owl service running?)", file=sys.stderr)
            return 1
        try:
            log.info("receiving via AirDrop on %s (files land in ~/.opendrop)", iface)
            awdl.receive_native(iface=iface)
        except awdl.AwdlError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    cfg = cfgmod.load(args.config_dir)
    if args.accept_policy:
        cfg.accept_policy = args.accept_policy
    _apply_overrides(cfg, args)
    if args.download_dir:
        cfg.download_dir = Path(args.download_dir).expanduser()
    run_receiver(cfg, cert_dir=cfgmod.config_dir(args.config_dir),
                 prompt=args.prompt and sys.stdin.isatty())
    return 0


def cmd_status(args) -> int:
    cfg = cfgmod.load(args.config_dir)
    fp = _fingerprint(cfg, args.config_dir)
    listening = False
    try:
        with socket.create_connection(("127.0.0.1", cfg.port), timeout=0.3):
            listening = True
    except OSError:
        pass
    print(f"alias:         {cfg.alias}")
    print(f"fingerprint:   {fp}")
    print(f"port:          {cfg.port} ({cfg.protocol})")
    print(f"download dir:  {cfg.download_dir.expanduser()}")
    print(f"accept policy: {cfg.accept_policy}")
    print(f"receiver:      {'running' if listening else 'not running'}")
    from airdropd import awdl

    ns = awdl.native_status()
    print(f"awdl iface:    {ns['interface'] or 'none'}")
    print(f"owl:           {'running' if ns['owl_running'] else 'not running'}")
    print(f"opendrop:      {'installed' if ns['opendrop'] else 'missing'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airdrop", description="AirDrop-style local file transfer (LocalSend v2 compatible)"
    )
    parser.add_argument("--version", action="version", version=f"airdrop {__version__}")
    parser.add_argument("--config-dir", help="override config directory")
    parser.add_argument("--port", type=int, help="override transfer port")
    parser.add_argument("--protocol", choices=("http", "https"), help="override protocol")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_peers = sub.add_parser("peers", help="discover nearby peers")
    p_peers.add_argument("--timeout", type=float, default=2.0)
    p_peers.add_argument("--airdrop", action="store_true",
                         help="also scan for native AirDrop receivers (needs opendrop + AWDL)")
    p_peers.add_argument("--iface", help="AWDL interface override")
    p_peers.set_defaults(fn=cmd_peers)

    p_send = sub.add_parser("send", help="send files to a peer")
    p_send.add_argument("files", nargs="+", metavar="FILE")
    p_send.add_argument("--to", help="peer alias or fingerprint substring")
    p_send.add_argument("--timeout", type=float, default=2.0)
    p_send.add_argument("--airdrop", action="store_true",
                        help="send via native AirDrop (needs opendrop + AWDL)")
    p_send.add_argument("--iface", help="AWDL interface override")
    p_send.set_defaults(fn=cmd_send)

    p_recv = sub.add_parser("receive", help="run the receiver")
    p_recv.add_argument("--prompt", action="store_true", help="ask before accepting")
    p_recv.add_argument("--download-dir")
    p_recv.add_argument("--accept-policy", choices=cfgmod.ACCEPT_POLICIES)
    p_recv.add_argument("--airdrop", action="store_true",
                        help="receive via native AirDrop (needs opendrop + AWDL)")
    p_recv.add_argument("--iface", help="AWDL interface override")
    p_recv.set_defaults(fn=cmd_receive)

    p_status = sub.add_parser("status", help="show configuration and receiver state")
    p_status.set_defaults(fn=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return args.fn(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
