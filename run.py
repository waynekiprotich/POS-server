"""
Start the POS.

    python run.py                 development server on 127.0.0.1:5001 (pair with `npm run dev`)
    python run.py --lan           shop mode: serves the built app on every network card, port 8080
    python run.py --lan --https   shop mode over HTTPS (live phone camera; self-signed certificate)

Shop mode runs one process with several threads. That is deliberate: phone
pairing and sign-in limits live in memory and must be shared by every request.
"""
import argparse
import atexit
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
CERT_DIR = os.path.join(INSTANCE_DIR, "certs")
PID_FILE = os.path.join(INSTANCE_DIR, "pos-server.pid")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the POS server.")
    parser.add_argument("--lan", action="store_true", help="shop mode on the local network")
    parser.add_argument("--host", default=None, help="address to bind (default 0.0.0.0 with --lan)")
    parser.add_argument("--port", type=int, default=None, help="port (8080 with --lan, else 5001)")
    parser.add_argument("--https", action="store_true", help="serve HTTPS with a local certificate")
    parser.add_argument("--threads", type=int, default=8, help="request threads in shop mode")
    return parser.parse_args()


def ensure_certificate(addresses):
    """Self-signed certificate for this computer's LAN addresses (made once)."""
    cert = os.path.join(CERT_DIR, "cert.pem")
    key = os.path.join(CERT_DIR, "key.pem")
    names = ["DNS:localhost", "IP:127.0.0.1"] + ["IP:%s" % a for a in addresses]
    marker = os.path.join(CERT_DIR, "names.txt")
    wanted = ",".join(names)
    try:
        with open(marker) as handle:
            current = handle.read().strip()
    except FileNotFoundError:
        current = ""
    if os.path.isfile(cert) and os.path.isfile(key) and current == wanted:
        return cert, key

    os.makedirs(CERT_DIR, exist_ok=True)
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", key, "-out", cert, "-days", "825",
                "-subj", "/CN=POS local server",
                "-addext", "subjectAltName=%s" % wanted,
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        sys.exit("Could not create an HTTPS certificate with openssl: %s" % error)
    os.chmod(key, 0o600)
    with open(marker, "w") as handle:
        handle.write(wanted)
    return cert, key


def print_banner(scheme, port, addresses):
    suffix = ":%d" % port
    print("")
    print("  POS is running.")
    print("")
    print("  On this computer:   %s://localhost%s" % (scheme, suffix))
    if addresses:
        for address in addresses:
            print("  On the shop Wi-Fi:  %s://%s%s" % (scheme, address, suffix))
    else:
        print("  On the shop Wi-Fi:  (no network found - connect this computer to Wi-Fi)")
    print("")
    print("  Keep this window open while the shop is trading. Press Ctrl+C to stop.")
    print("  Do not forward this port on your router; the POS is for the shop network only.")
    print("")
    sys.stdout.flush()


def ensure_port_free(host, port):
    """Stop before printing anything if another program (or POS) holds the port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # Same option gunicorn uses, so connections still closing from the last
        # run do not count as "in use"; a live listener on the port still does.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            sys.exit(
                "Port %d is already in use - is the POS already running in another "
                "window? Stop it first, or start with --port <another port>." % port
            )


def write_pid():
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    with open(PID_FILE, "w") as handle:
        handle.write(str(os.getpid()))

    def remove():
        try:
            with open(PID_FILE) as handle:
                if handle.read().strip() == str(os.getpid()):
                    os.remove(PID_FILE)
        except OSError:
            pass

    atexit.register(remove)


def run_lan(args):
    os.environ["POS_BACKGROUND_JOBS"] = "1"
    os.environ.setdefault("FLASK_ENV", "production")

    from gunicorn.app.base import BaseApplication

    from app import create_app
    from app.utils.network import lan_ipv4_addresses

    host = args.host or "0.0.0.0"
    # Not 5000: macOS uses it for AirPlay Receiver.
    port = args.port or 8080
    ensure_port_free(host, port)
    addresses = lan_ipv4_addresses()
    options = {
        "bind": "%s:%d" % (host, port),
        "workers": 1,
        "worker_class": "gthread",
        "threads": args.threads,
        "timeout": 120,
        "accesslog": None,
        "errorlog": "-",
        "loglevel": "warning",
    }
    scheme = "http"
    if args.https:
        cert, key = ensure_certificate(addresses)
        options.update({"certfile": cert, "keyfile": key})
        scheme = "https"

    class PosServer(BaseApplication):
        def load_config(self):
            for name, value in options.items():
                self.cfg.set(name, value)

        def load(self):
            return create_app()

    write_pid()
    print_banner(scheme, port, addresses)
    PosServer().run()


def run_dev(args):
    from app import create_app

    app = create_app()
    app.run(host=args.host or "127.0.0.1", port=args.port or 5001, debug=True)


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.lan:
        run_lan(arguments)
    else:
        run_dev(arguments)
else:
    # `flask --app run.py ...` and gunicorn "run:app" import this module.
    from app import create_app

    app = create_app()
