"""Attach an expiring relay invitation to a clean FounderRadar jury ZIP."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path, PurePosixPath
import secrets
from urllib.parse import urlsplit
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Clean FounderRadar ZIP")
    parser.add_argument("endpoint", help="HTTPS address of the FounderRadar AI relay")
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--budget", type=int, default=80)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--relay-env", type=Path, required=True, help="Operator-only environment file")
    args = parser.parse_args()
    url = urlsplit(args.endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error("Specify an HTTPS address without credentials, query or fragment.")
    if not 1 <= args.hours <= 168 or not 1 <= args.budget <= 1_000:
        parser.error("Maximum invitation lifetime is 168 hours and maximum budget is 1,000 calls.")
    if len({args.archive.resolve(), args.output.resolve(), args.relay_env.resolve()}) != 3:
        parser.error("Use separate paths for the input ZIP, output ZIP and relay settings.")
    if args.output.exists() or args.relay_env.exists():
        parser.error("Output files already exist. Choose fresh file names.")
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=args.hours)).isoformat()
    with zipfile.ZipFile(args.archive) as source:
        paths = [PurePosixPath(entry) for entry in source.namelist()]
        root = {path.parts[0] for path in paths if path.parts}
        if len(root) != 1 or any(path.is_absolute() or ".." in path.parts for path in paths):
            parser.error("The input ZIP must have one safe root directory.")
        if any(path.name in {"jury-access.json", "ai-relay.env", ".env", "secrets.toml"}
               or path.suffix in {".sqlite3", ".db"} for path in paths):
            parser.error("The input ZIP must be the clean, unconfigured distribution.")
        root_dir = root.pop()
        if f"{root_dir}/Start-FounderRadar.cmd" not in source.namelist():
            parser.error("The input ZIP is missing the FounderRadar launcher.")
        with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as release:
            for entry in source.infolist():
                release.writestr(entry, source.read(entry))
            release.writestr(f"{root_dir}/jury-access.json",
                             json.dumps({"endpoint": args.endpoint.rstrip("/"), "token": token}))
    with args.relay_env.open("x", encoding="utf-8") as env:
        env.write(f"FOUNDERRADAR_JURY_TOKEN={token}\nFOUNDERRADAR_JURY_EXPIRES={expires}\n"
                  f"FOUNDERRADAR_AI_BUDGET={args.budget}\n")
    print(f"Jury-ZIP: {args.output}\nServer-Konfiguration: {args.relay_env}\nAblauf: {expires}")


if __name__ == "__main__":
    main()
