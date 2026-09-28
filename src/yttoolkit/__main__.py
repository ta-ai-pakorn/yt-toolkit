from __future__ import annotations

import argparse
import sys

from . import lifecycle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yttoolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="เปิดโปรแกรม (tray + เบราว์เซอร์)")
    sub.add_parser("stop", help="ปิดโปรแกรม")
    serve = sub.add_parser("serve", help="รันเซิร์ฟเวอร์อย่างเดียว (พัฒนา/เทส)")
    serve.add_argument("--port", type=int)
    serve.add_argument("--dev", action="store_true", help="อนุญาต origin ของ Vite dev server")
    args = parser.parse_args(argv)
    if args.command == "start":
        return lifecycle.start()
    if args.command == "stop":
        return lifecycle.stop()
    return lifecycle.serve(port=args.port, dev=args.dev)


if __name__ == "__main__":
    sys.exit(main())
