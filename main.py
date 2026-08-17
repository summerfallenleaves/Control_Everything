"""Control_Everything 的 CLI 入口。

对设备运行自主 GUI Agent：

  uv run python main.py --goal "打开 Safari" --platform macos
  uv run python main.py --goal "..." --platform macos --llm dummy  # 离线冒烟测试
  uv run python main.py --platform macos --inspect                  # 仅导出 UI 树
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")  # 项目 .env，按用途命名变量


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
    raise SystemExit(f'未知平台: {platform}')


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
    parser.add_argument('--goal', help='Agent 的任务，例如 "打开 Safari"')
    parser.add_argument('--llm', choices=['auto', 'dummy'], default='auto',
                help="'dummy' = 离线冒烟测试；'auto' = 使用 .env 的 DECISION_PROVIDER")
    parser.add_argument('--model', default=None, help='覆盖 .env 的 DECISION_MODEL')
    parser.add_argument('--provider', default=None, help='覆盖 DECISION_PROVIDER（anthropic|openai）')
    parser.add_argument('--max-steps', type=int, default=20)
    parser.add_argument('--no-verify', action='store_true', help='禁用步骤验证')
    parser.add_argument('--no-screenshot', action='store_true', help='跳过截图')
    parser.add_argument('--no-vision', action='store_true', help='禁用视觉模型')
    parser.add_argument('--no-confirm', action='store_true', help='关闭危险动作确认（仅建议自动化测试时使用）')
    parser.add_argument('--no-plan', action='store_true', help='关闭任务规划')
    parser.add_argument('--inspect', action='store_true', help='导出 UI 树后退出')
    args = parser.parse_args(argv)

    if args.inspect:
        _inspect(args.platform)
        return 0

    if not args.goal:
        parser.error('除非使用 --inspect，否则 --goal 必填')

    backend = _make_backend(args.platform, screenshot=not args.no_screenshot)
    from llm.client import get_client
    name = 'dummy' if args.llm == 'dummy' else None
    llm = get_client(
        purpose='decision', name=name, provider=args.provider, model=args.model
    )

    vision = None
    if not args.no_vision and not args.no_screenshot:
        try:
            vision = get_client(purpose='vision')
            print(f'视觉已启用: {type(vision).__name__} model={vision.model}')
        except Exception as e:
            print(f'视觉已禁用: {e}')

    try:
        vision_interval = max(1, int(os.getenv('VISION_INTERVAL', '3')))
    except ValueError:
        vision_interval = 3

    def cli_confirm(action=None, ask_mode: bool = False):
        """CLI 确认回调：危险动作确认 + ask_user 自由提问。"""
        if ask_mode:
            question = action if isinstance(action, str) else ''
            print(f'❓ Agent 提问: {question}')
            return input('你的回答（直接回车 = 无回答）: ').strip()
        print('⚠️ 危险动作需要确认:')
        print(f'   动作: [{action.kind}] {action.to_dict()}')
        print('   [y] 允许并记住  [n] 拒绝并记住  [o] 仅本次允许  [c] 仅本次拒绝  [回车] 拒绝')
        return input('选择: ').strip().lower()

    planner = None
    if not args.no_plan:
        try:
            plan_client = get_client(purpose='planning')
            from core.planner import Planner
            planner = Planner(plan_client)
            print(f'规划器已启用: {type(plan_client).__name__} model={plan_client.model}')
        except Exception as e:
            print(f'规划器禁用: {e}')

    from core.orchestrator import AgentOrchestrator
    confirm_cb = None if args.no_confirm else cli_confirm
    orch = AgentOrchestrator(
        backend, llm, max_steps=args.max_steps, verify=not args.no_verify,
        vision=vision, vision_interval=vision_interval,
        confirm_callback=confirm_cb, planner=planner,
    )
    result = orch.run(args.goal)

    print(f'目标: {result.goal}')
    print(f'成功: {result.ok}  步数: {result.steps}  耗时: {result.duration_s:.1f}s')
    if result.last_error:
        print(f'错误: {result.last_error}')
    print('--- 历史 ---')
    for h in result.history:
        print(' ', h)
    return 0 if result.ok else 1


if __name__ == '__main__':
    sys.exit(main())
