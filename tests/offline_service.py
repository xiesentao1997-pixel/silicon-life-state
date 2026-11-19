"""Install the offline acceptance policy in the service interpreter before its entrypoint.

Invoked by test_acceptance.py. Does not rely on site packages, .pth, PYTHONPATH
or automatic loading of sitecustomize. It restricts this Python service's sockets,
not the operating system or other applications.
"""
import ipaddress
import json
import os
from pathlib import Path
import runpy
import socket
import sys


class NetworkDisabled(OSError):
    """The tested application attempted to leave loopback."""


def is_loopback(host):
    if isinstance(host, bytes):
        host = host.decode('ascii', errors='replace')
    if host in (None, 'localhost'):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_guard():
    observations = Path(os.environ['SLS_TEST_NETWORK_LOG'])
    testing_policy = True

    def check(event, args):
        if event == 'socket.getaddrinfo':
            host = args[0]
        elif event in ('socket.connect', 'socket.sendto', 'socket.sendmsg') and isinstance(args[1], tuple):
            host = args[1][0]
        else:
            return
        if not is_loopback(host):
            with observations.open('a', encoding='utf-8') as log:
                log.write(json.dumps({'event': event, 'self_test': testing_policy}) + '\n')
            raise NetworkDisabled('External networking is unavailable in this acceptance process.')

    sys.addaudithook(check)
    # Check the rejection on actual stdlib calls. A policy miss raises a different
    # exception and aborts startup, so a silent "network unavailable" cannot pass.
    probes = [lambda: socket.getaddrinfo('acceptance.invalid', 443)]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        tcp.settimeout(0.5)
        probes.append(lambda: tcp.connect(('192.0.2.1', 443)))
        for probe in probes:
            try:
                probe()
            except NetworkDisabled:
                continue
            raise RuntimeError('Offline policy did not reject its negative control')

    testing_policy = False


if __name__ == '__main__':
    install_guard()
    # Use exactly the packaged service, with the service's normal option parser.
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name='__main__')
