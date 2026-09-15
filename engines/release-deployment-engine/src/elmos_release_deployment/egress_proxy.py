"""Bounded CONNECT/TLS-SNI gateway for a host-provisioned private worker network.

Endpoints are exact host/IP pins from trusted installation, never client DNS.
The host guard must enforce current scope, authorization and lease revocation.
"""
import ipaddress
import re
import select
import socket
import socketserver
import threading
import time
from .contracts import require


def client_hello_name(record):
    require(len(record) >= 9 and record[0] == 22 and record[1:3] in (b'\x03\x01',b'\x03\x03')
            and int.from_bytes(record[3:5],'big') == len(record)-5, 'egress_tls_record')
    data=record[5:]
    require(data[0] == 1 and int.from_bytes(data[1:4],'big') == len(data)-4, 'egress_client_hello')
    position=4
    def take(n):
        nonlocal position
        require(0 <= n <= len(data)-position, 'egress_hello_bounds')
        result=data[position:position+n]; position+=n; return result
    def number(n): return int.from_bytes(take(n),'big')
    take(34); take(number(1))
    cipher_size=number(2); require(cipher_size >= 2 and cipher_size % 2 == 0, 'egress_cipher_list'); take(cipher_size)
    take(number(1)); size=number(2)
    require(size == len(data)-position, 'egress_extension_bounds')
    host=None; seen=set()
    while position < len(data):
        kind=number(2); value=take(number(2))
        require(kind not in seen and kind != 0xfe0d, 'egress_duplicate_or_encrypted_hello'); seen.add(kind)
        if kind == 0:
            require(len(value) >= 5 and int.from_bytes(value[:2],'big') == len(value)-2
                    and value[2] == 0 and int.from_bytes(value[3:5],'big') == len(value)-5, 'egress_sni_format')
            host=value[5:].decode('ascii')
    require(host is not None and re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]',host), 'egress_sni_required')
    return host


def receive_exact(connection, size, deadline=None):
    result=bytearray()
    while len(result) < size:
        if deadline is not None:
            remaining=deadline-time.monotonic(); require(remaining > 0,'egress_receive_deadline')
            connection.settimeout(min(5,remaining))
        chunk=connection.recv(size-len(result)); require(bool(chunk),'egress_early_eof'); result.extend(chunk)
    return bytes(result)


class EgressProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address=False
    daemon_threads=True
    def __init__(self, address, endpoints, guard):
        require(callable(guard) and 0 < len(endpoints) <= 64, 'egress_configuration')
        self.endpoints=dict(endpoints); self.guard=guard
        for host,ip in self.endpoints.items():
            pinned_address=ipaddress.ip_address(ip)
            require(type(host) is str and re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]',host)
                    and pinned_address.is_global and not pinned_address.is_multicast and not pinned_address.is_reserved, 'egress_public_endpoint_pin')
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(address,ProxyHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False): self.shutdown_request(request); return
        try: super().process_request(request,client_address)
        except BaseException: self.slots.release(); raise

    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request,client_address)
        finally: self.slots.release()

    def handle_error(self, request, client_address):
        # Never log request bodies, TLS bytes or credential-bearing payloads.
        pass


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        client=self.request; client.settimeout(5)
        upstream=None
        try:
            self.server.guard()
            header=bytearray()
            header_deadline=time.monotonic()+5
            while not header.endswith(b'\r\n\r\n'):
                require(len(header) < 8192, 'egress_header_bounds')
                header.extend(receive_exact(client,1,header_deadline))
            lines=bytes(header).split(b'\r\n')
            match=re.fullmatch(rb'CONNECT ([a-z0-9][a-z0-9.-]{0,251}[a-z0-9]):443 HTTP/1\.[01]',lines[0])
            require(match is not None,'egress_connect_only')
            host=match[1].decode('ascii'); require(host in self.server.endpoints,'egress_host_not_allowed')
            for line in lines[1:-2]:
                name,separator,value=line.partition(b':')
                require(separator and name.lower() != b'transfer-encoding'
                        and (name.lower() != b'content-length' or value.strip() == b'0'), 'egress_request_body')
            client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            hello_deadline=time.monotonic()+5
            header=receive_exact(client,5,hello_deadline); size=int.from_bytes(header[3:5],'big')
            require(0 < size <= 16384,'egress_tls_bounds')
            hello=header+receive_exact(client,size,hello_deadline)
            require(client_hello_name(hello) == host, 'egress_sni_mismatch')
            self.server.guard()
            ip=self.server.endpoints[host]
            upstream=socket.socket(socket.AF_INET6 if ':' in ip else socket.AF_INET,socket.SOCK_STREAM)
            upstream.settimeout(5); upstream.connect((ip,443)); upstream.sendall(hello)
            deadline=time.monotonic()+300; transferred=0
            while time.monotonic() < deadline:
                self.server.guard()
                ready,_,_=select.select([client,upstream],[],[],0.25)
                for source in ready:
                    data=source.recv(65536)
                    if not data: return
                    transferred+=len(data); require(transferred <= 67108864, 'egress_transfer_budget')
                    (upstream if source is client else client).sendall(data)
        except Exception:
            # A failed tunnel is closed, never retried or redirected.
            pass
        finally:
            if upstream is not None: upstream.close()
