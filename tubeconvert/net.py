"""Forzatura della famiglia di indirizzi (porting di IpFamily/IpFamilyDns).

Il CDN di YouTube lega l'URL all'IP che l'ha richiesto: in caso di 403 si
ripete il trasferimento forzando IPv4 e poi IPv6.
"""
from __future__ import annotations

import enum
import socket
import threading

import requests
import urllib3.util.connection as _u3conn


class IpFamily(enum.Enum):
    ANY = "ANY"
    IPV4 = "IPV4"
    IPV6 = "IPV6"


_local = threading.local()
_orig_allowed = _u3conn.allowed_gai_family


def _allowed_gai_family():
    fam = getattr(_local, "family", IpFamily.ANY)
    if fam == IpFamily.IPV4:
        return socket.AF_INET
    if fam == IpFamily.IPV6:
        return socket.AF_INET6
    return _orig_allowed()


_u3conn.allowed_gai_family = _allowed_gai_family


class use_family:
    """Context manager: forza la famiglia di indirizzi nel thread corrente."""

    def __init__(self, family: IpFamily):
        self.family = family

    def __enter__(self):
        self.prev = getattr(_local, "family", IpFamily.ANY)
        _local.family = self.family
        return self

    def __exit__(self, *exc):
        _local.family = self.prev
        return False


def session_for_family(_family: IpFamily) -> requests.Session:
    s = requests.Session()
    # connessioni non condivise tra famiglie diverse
    s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    return s
