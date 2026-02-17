"""Quick smoke check for LLM gateway wiring.

This script does not execute model calls unless --call is passed.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infra.llm.gateway import get_llm_gateway
from src.infra.llm.models import LLMChatRequest


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call", action="store_true", help="Execute a real API call")
    args = parser.parse_args()

    gateway = get_llm_gateway()
    print("metrics:", gateway.get_metrics_snapshot())

    if args.call:
        req = LLMChatRequest(messages=[{"role": "user", "content": "hello"}], timeout_s=60)
        resp = await gateway.chat(req)
        print("response model:", getattr(resp, "model", "unknown"))
        print("response preview:", str(getattr(resp, "content", ""))[:120])


if __name__ == "__main__":
    asyncio.run(main())
