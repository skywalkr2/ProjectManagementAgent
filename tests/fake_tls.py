"""A throwaway certificate authority and a server certificate for 127.0.0.1, made with the `openssl` command line, so
the fake services can answer over HTTPS and the app can be made to trust them the standard way: by pointing
`SSL_CERT_FILE` at the authority's certificate. Nothing is trusted outside the process that is given that variable.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

ADDRESS = "127.0.0.1"
DAYS = "2"

#: What a strict verifier (the standard library's default) expects of a server certificate.
SERVER_EXTENSIONS = (
    f"subjectAltName=IP:{ADDRESS}\n"
    "basicConstraints=critical,CA:FALSE\n"
    "keyUsage=critical,digitalSignature,keyEncipherment\n"
    "extendedKeyUsage=serverAuth\n"
    "authorityKeyIdentifier=keyid\n"
    "subjectKeyIdentifier=hash\n"
)


@dataclass(frozen=True)
class Certificates:
    authority: Path  # the certificate to trust (SSL_CERT_FILE)
    certificate: Path  # the server's certificate
    key: Path  # the server's private key


def _run(*command: str) -> None:
    done = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - a fixed openssl call
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:3])} failed: {done.stderr.strip()[-300:]}")


def make(folder: Path) -> Certificates:
    """The authority and the server certificate it signs, written into `folder` (made again each time)."""
    folder.mkdir(parents=True, exist_ok=True)
    found = Certificates(folder / "authority.pem", folder / "server.pem", folder / "server.key")
    authority_key, request, extensions = folder / "authority.key", folder / "server.csr", folder / "server.ext"
    _run(
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", DAYS,
        "-keyout", str(authority_key), "-out", str(found.authority), "-subj", "/CN=Journey test authority",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-addext", "subjectKeyIdentifier=hash",
    )  # fmt: skip
    _run(
        "openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(found.key), "-out", str(request),
        "-subj", f"/CN={ADDRESS}",
    )  # fmt: skip
    extensions.write_text(SERVER_EXTENSIONS, encoding="utf-8")
    _run(
        "openssl", "x509", "-req", "-in", str(request), "-CA", str(found.authority), "-CAkey", str(authority_key),
        "-CAcreateserial", "-out", str(found.certificate), "-days", DAYS, "-extfile", str(extensions),
    )  # fmt: skip
    return found
