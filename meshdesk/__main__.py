from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="MeshDesk local Meshtastic UI")
    parser.add_argument("--host", default="127.0.0.1", help="UI listen address")
    parser.add_argument("--port", type=int, default=8765, help="UI listen port")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()
    uvicorn.run("meshdesk.app:app", host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
