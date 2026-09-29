from __future__ import annotations

import argparse
import logging
import sys

log = logging.getLogger("yttoolkit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yttoolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="เปิดโปรแกรม (tray + เบราว์เซอร์)")
    sub.add_parser("stop", help="ปิดโปรแกรม")
    wait = sub.add_parser("wait", help="รอจนโปรแกรมเปิดเสร็จ แล้วบอกผล")
    wait.add_argument("--timeout", type=float, default=25.0, help="จำนวนวินาทีที่รอ (ค่าเริ่มต้น 25, 0 = เช็กครั้งเดียว)")
    serve = sub.add_parser("serve", help="รันเซิร์ฟเวอร์อย่างเดียว (พัฒนา/เทส)")
    serve.add_argument("--port", type=int)
    serve.add_argument("--dev", action="store_true", help="อนุญาต origin ของ Vite dev server")
    args = parser.parse_args(argv)
    # import เฉพาะที่แต่ละคำสั่งใช้ ถ้าไลบรารีของเว็บหายหรือพัง wait ยังตอบเป็นภาษาไทย และ start ยังเขียน log ได้
    if args.command == "wait":
        from . import probe

        return probe.wait(timeout=args.timeout)
    if args.command == "start":
        return _start()
    if args.command == "stop":
        from . import probe
        from .config import default_paths

        probe.setup_file_log(default_paths())  # stop บอกให้ไปดู app.log จึงต้องเขียนรายละเอียดลงไฟล์นั้นด้วย
        from . import lifecycle

        return lifecycle.stop()
    from . import lifecycle

    return lifecycle.serve(port=args.port, dev=args.dev)


def _start() -> int:
    from . import probe
    from .config import default_paths

    # ตั้ง log ก่อน import lifecycle (ซึ่งโหลด uvicorn และ FastAPI) ถ้า import พัง traceback จะลง app.log
    probe.setup_file_log(default_paths())
    try:
        from . import lifecycle

        return lifecycle.start()
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException:
        log.exception("เปิดโปรแกรมไม่สำเร็จ")
        return 1


if __name__ == "__main__":
    sys.exit(main())
