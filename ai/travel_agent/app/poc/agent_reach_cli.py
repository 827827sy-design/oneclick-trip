from __future__ import annotations

import argparse
import sys

from app.tools.research import (
    AgentReachDiagnostics,
    AgentReachResearchCoordinator,
    AgentReachWebFetch,
    AgentReachWebSearch,
    ResearchResultCache,
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Agent Reach web-research PoC")
    parser.add_argument("query", nargs="?", help="Research query, for example 峨眉山徒步攻略")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--doctor", action="store_true", help="Only inspect channel status")
    parser.add_argument("--official-domain", action="append", default=[])
    parser.add_argument("--trusted-domain", action="append", default=[])
    parser.add_argument("--fetch-top", type=int, default=0, choices=range(0, 6))
    args = parser.parse_args()

    if args.doctor:
        result = AgentReachDiagnostics().check()
    else:
        cache = ResearchResultCache()
        result = AgentReachResearchCoordinator(
            AgentReachWebSearch(cache=cache),
            AgentReachWebFetch(cache=cache),
        ).research(
            args.query or "",
            official_domains=args.official_domain,
            trusted_domains=args.trusted_domain,
            limit=args.limit,
            fetch_top=args.fetch_top,
        )
    print(result.model_dump_json(indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
