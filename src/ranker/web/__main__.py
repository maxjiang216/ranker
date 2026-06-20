"""Launch the localhost web app: ``python -m ranker.web [--port 8000] [--data DIR]``."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ranker web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default=None, help="Library folder (default ./ranker-data)")
    args = parser.parse_args()

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(args.data), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
