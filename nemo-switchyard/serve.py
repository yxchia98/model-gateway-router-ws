"""Host Switchyard's native server and expose its loopback listener in Docker."""
import argparse
import signal
import subprocess
import threading

from switchyard_rust.server import Server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Load and validate routes without upstream calls")
    args = parser.parse_args()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    # The Python binding exposes the same native Rust server, on loopback only.
    with Server("/app/routes.toml", port=4001):
        if args.check:
            print("Switchyard configuration loaded successfully")
            return
        proxy = subprocess.Popen([
            "socat", "TCP-LISTEN:4000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:127.0.0.1:4001",
        ])
        try:
            print("Switchyard listening on :4000; routes: direct, weighted-random, system-one, llm-classifier, custom-selector, session-pinned, advisor-review", flush=True)
            while not stop.wait(0.5):
                if proxy.poll() is not None:
                    raise RuntimeError("Container TCP listener exited")
        finally:
            if proxy.poll() is None:
                proxy.terminate()
                try:
                    proxy.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy.kill()
                    proxy.wait()


if __name__ == "__main__":
    main()
