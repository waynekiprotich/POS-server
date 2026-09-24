"""Find the addresses other devices on the shop network can use."""
import ipaddress
import socket


def _is_lan(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local


def lan_ipv4_addresses():
    """Private IPv4 addresses of this computer, the most likely one first.

    Opening a UDP socket towards a private address sends no packets; it only
    asks the OS which network card it would use, which is the Wi-Fi/LAN card.
    """
    found = []
    for probe in ("10.255.255.255", "192.168.255.255", "172.31.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((probe, 1))
                address = sock.getsockname()[0]
        except OSError:
            continue
        if _is_lan(address) and address not in found:
            found.append(address)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if _is_lan(address) and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


def lan_urls(scheme, port, override=""):
    if override:
        return [override.rstrip("/")]
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    suffix = "" if default_port else ":%d" % port
    return ["%s://%s%s" % (scheme, address, suffix) for address in lan_ipv4_addresses()]
