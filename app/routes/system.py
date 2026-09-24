from flask import Blueprint, current_app, jsonify, request

from ..utils.auth import auth_required
from ..utils.network import lan_ipv4_addresses, lan_urls

bp = Blueprint("system", __name__, url_prefix="/api/system")


@bp.get("/network")
@auth_required
def network():
    """Addresses phones and other tills on the same Wi-Fi can open."""
    host = request.host
    port = request.environ.get("SERVER_PORT")
    if ":" in host and not host.endswith("]"):
        port = host.rsplit(":", 1)[1]
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 443 if request.scheme == "https" else 80
    urls = lan_urls(request.scheme, port, current_app.config.get("LAN_URL", ""))
    hostname = request.host.split(":")[0]
    return jsonify(
        {
            "lan_urls": urls,
            # The browser rebuilds links from these with its own port, which also
            # works behind the Vite dev server.
            "lan_addresses": lan_ipv4_addresses(),
            "lan_url_override": current_app.config.get("LAN_URL") or None,
            "current_origin": request.host_url.rstrip("/"),
            "on_localhost": hostname in ("localhost", "127.0.0.1", "::1"),
            "secure": request.scheme == "https",
        }
    )
