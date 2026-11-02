"""Dashboard se syntetickými daty: python -m demo.demo_web  → http://localhost:5000"""
import tempfile
from pathlib import Path

from daemon.analyzer import Analyzer
from daemon.notifier import Notifier
from demo.demo import build_demo_db
from web.app import create_app


def main():
    db = build_demo_db(str(Path(tempfile.mkdtemp()) / "demo.db"))
    Notifier(db, {"enabled": True}).process(Analyzer(db).run())
    print("Dashboard: http://localhost:5000")
    create_app(db, {}).run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
