"""Server mode: REST API + web panel, no desktop window. Browsers run hidden.

    python -m src.server [--host 127.0.0.1] [--port 8000]

Exposing it beyond this machine requires FOXPROFILE_API_TOKEN.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description="FoxProfile server (API + web panel)")
    parser.add_argument("--host", help="Interface to listen on (default: FOXPROFILE_API_HOST)")
    parser.add_argument("--port", type=int, help="Port (default: FOXPROFILE_API_PORT)")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show browser windows instead of running them hidden",
    )
    args = parser.parse_args()

    # Must be decided before src.core.config is imported; runner subprocesses
    # inherit it through the environment.
    if args.headed:
        os.environ["FOXPROFILE_HEADLESS"] = "false"
    else:
        os.environ.setdefault("FOXPROFILE_HEADLESS", "true")

    import uvicorn

    from src.api.app import create_app
    from src.api.auth import check_bind_safety
    from src.core.config import API_HOST, API_PORT, API_TOKEN
    from src.core.container import Container
    from src.core.logging import get_logger

    host = args.host or API_HOST
    port = args.port or API_PORT
    check_bind_safety(host, API_TOKEN)

    container = Container()
    app = create_app(container)
    logger = get_logger("server")
    logger.info("FoxProfile server on http://%s:%s (panel at /)", host, port)
    print(f"FoxProfile panel: http://{host}:{port}/   API docs: http://{host}:{port}/docs")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        container.browser_launcher.shutdown_all()


if __name__ == "__main__":
    main()
