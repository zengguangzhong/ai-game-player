"""入口:python main.py --game example

--game      游戏名,对应 rules/<game>.yaml
--rules-dir 规则目录,默认 ./rules
--dry-run   只解析规则不执行,用于校验 yaml 写得对不对
"""
import sys
import argparse
from pathlib import Path

import yaml

from rules import GameConfig
from engine import Engine


def load_config(game: str, rules_dir: Path) -> GameConfig:
    path = rules_dir / f"{game}.yaml"
    if not path.exists():
        print(f"找不到规则文件: {path}")
        print(f"可用规则: {[p.stem for p in rules_dir.glob('*.yaml')]}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return GameConfig.from_dict(data)


def main():
    parser = argparse.ArgumentParser(description="抖音小游戏自动玩框架")
    parser.add_argument("--game", required=True, help="游戏名(对应 rules/<game>.yaml)")
    parser.add_argument("--rules-dir", default="rules", help="规则目录")
    parser.add_argument("--dry-run", action="store_true", help="只解析不执行")
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    cfg = load_config(args.game, rules_dir)

    print(f"游戏: {cfg.game}")
    print(f"窗口: '{cfg.window_title or '全屏'}'")
    print(f"规则: {len(cfg.rules)} 条")
    for r in cfg.rules:
        print(f"  - {r.name}")

    if args.dry_run:
        print("\n[dry-run] 规则解析成功,未执行")
        return

    engine = Engine(cfg)
    engine.start()


if __name__ == "__main__":
    main()
