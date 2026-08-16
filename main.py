"""Control_Everything CLI entry point.

Run an autonomous GUI agent against a device:

  uv run python main.py --goal "open Safari" --platform macos
  uv run python main.py --goal "..." --platform macos --llm dummy  # offline smoke test
  uv run python main.py --platform macos --inspect                  # dump UI tree only
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # .env -> env vars, named by purpose (DECISION_MODEL etc.)


def _make_backend(platform: str, screenshot: bool):
    if platform == 'macos':
        from backends.macos import MacOSBackend
        return MacOSBackend(screenshot=screenshot)
    if platform == 'android':
        from backends.android import AndroidBackend
        return AndroidBackend()
    if platform == 'ios':
        from backends.ios import IOSBackend
        return IOSBackend()
    raise SystemExit(f'unknown platform: {platform}')


def _inspect(platform: str):
    backend = _make_backend(platform, screenshot=False)
    state = backend.perceive()
    print(f'platform={state.platform} app={state.app!r}')

    def walk(e, d):
        b = e.bounds
        bstr = f'[{b.x:.0f},{b.y:.0f} {b.w:.0f}x{b.h:.0f}]' if b else ''
        line = f"{'  ' * d}- {e.ref} role={e.role}"
        if e.text:
            line += f' text={e.text[:50]!r}'
        if bstr:
            line += f' {bstr}'
        print(line)
        for c in e.children:
            walk(c, d + 1)

    walk(state.tree, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='control-everything')
    parser.add_argument('--platform', choices=['macos', 'android', 'ios'], default='macos')
    parser.add_argument('--goal', help='task for the agent, e.g. "open Safari"')
    parser.add_argument('--llm', choices=['auto', 'dummy'], default='auto',
                help="'dummy' = offline smoke test; 'auto' = use .env DECISION_PROVIDER")
    parser.add_argument('--model', default=None, help='override DECISION_MODEL from .env')
    parser.add_argument('--provider', default=None, help='override DECISION_PROVIDER (anthropic|openai)')
    parser.add_argument('--max-steps', type=int, default=20)
    parser.add_argument('--no-verify', action='store_true', help='disable step verification')
    parser.add_argument('--no-screenshot', action='store_true', help='skip screenshots')
    parser.add_argument('--inspect', action='store_true', help='dump the UI tree and exit')
    args = parser.parse_args(argv)

    if args.inspect:
        _inspect(args.platform)
        return 0

    if not args.goal:
        parser.error('--goal is required unless --inspect is used')

    backend = _make_backend(args.platform, screenshot=not args.no_screenshot)
    from llm.client import get_client
    name = 'dummy' if args.llm == 'dummy' else None
    llm = get_client(
        purpose='decision', name=name, provider=args.provider, model=args.model
    )

    from core.orchestrator import AgentOrchestrator
    orch = AgentOrchestrator(backend, llm, max_steps=args.max_steps, verify=not args.no_verify)
    result = orch.run(args.goal)

    print(f'goal: {result.goal}')
    print(f'ok: {result.ok}  steps: {result.steps}  duration: {result.duration_s:.1f}s')
    if result.last_error:
        print(f'error: {result.last_error}')
    print('--- history ---')
    for h in result.history:
        print(' ', h)
    return 0 if result.ok else 1


if __name__ == '__main__':
    sys.exit(main())
