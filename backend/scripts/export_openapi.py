#!/usr/bin/env python3
"""OpenAPI スキーマをエクスポートするスクリプト

Usage:
    cd backend && uv run python scripts/export_openapi.py [output_path]

デフォルトでは ../docs/openapi.json に出力する。
"""

import json
import os
import sys
from pathlib import Path

# backend/ ディレクトリをパスに追加（モジュール解決のため）
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.main import app


def main() -> None:
    # 出力先を決定
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
    else:
        output_path = Path(__file__).parent.parent.parent / "docs" / "openapi.json"

    # OpenAPI スキーマを取得
    schema = app.openapi()

    # JSON として出力
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"OpenAPI schema exported to: {output_path}")


if __name__ == "__main__":
    main()
