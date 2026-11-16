import argparse
import logging

import httpx

from agent.client import AgentClient
from agent.config import Config
from agent.runner import Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll for collect_system_info tasks")
    parser.add_argument("--once", action="store_true", help="Process at most one task, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        config = Config.from_env()
    except ValueError as exc:
        logging.error("%s", exc)
        return 1
    try:
        with httpx.Client(trust_env=False) as http:
            return Runner(AgentClient(config, http)).run(once=args.once)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
