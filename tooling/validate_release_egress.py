"""Explicit read-only public HTTPS probe through the real deployment egress proxy."""
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engines/release-deployment-engine/src'))
from elmos_release_deployment.egress_proxy import EgressProxy


def main():
    host='www.alibabacloud.com'
    paths=[ROOT/'engines/release-deployment-engine/src/elmos_release_deployment/egress_proxy.py',
           ROOT/'engines/release-deployment-engine/src/elmos_release_deployment/contracts.py',Path(__file__)]
    def hashes(): return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before=hashes(); result={'host':host,'method':'HEAD','path':'/','credentials_used':False}
    passed=False
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        candidates=sorted({entry[4][0] for entry in addresses})
        result['resolved_addresses']=candidates
        approved=[ip for ip in candidates if ipaddress.ip_address(ip).is_global
                  and not ipaddress.ip_address(ip).is_multicast
                  and not ipaddress.ip_address(ip).is_reserved]
        if not approved:
            result['failure_reason']='DNS_RETURNED_NO_PUBLIC_ENDPOINT'
            raise RuntimeError('no_public_endpoint')
        ip=approved[0]
        result['ip']=ip
        with EgressProxy(('127.0.0.1',0),{host:ip},lambda:None) as proxy:
            worker=threading.Thread(target=proxy.serve_forever,daemon=True); worker.start()
            try:
                with socket.create_connection(proxy.server_address,timeout=10) as connection:
                    connection.sendall(('CONNECT '+host+':443 HTTP/1.1\r\n\r\n').encode())
                    header=b''
                    while not header.endswith(b'\r\n\r\n') and len(header)<1024:
                        part=connection.recv(1)
                        if not part: raise RuntimeError('proxy_closed')
                        header+=part
                    if not header.startswith(b'HTTP/1.1 200'): raise RuntimeError('proxy_rejected')
                    with ssl.create_default_context().wrap_socket(connection,server_hostname=host) as tls:
                        result['tls_version']=tls.version()
                        result['peer_certificate_sha256']=hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
                        tls.sendall(('HEAD / HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\n\r\n').encode())
                        response=b''
                        while b'\r\n' not in response and len(response)<1024:
                            part=tls.recv(1024)
                            if not part: break
                            response+=part
                        status=response.split(b'\r\n',1)[0].decode('ascii')
                        result['http_status']=status
                        passed=status.startswith('HTTP/1.') and 200 <= int(status.split()[1]) < 500
            finally: proxy.shutdown(); worker.join(5)
    except Exception as error:
        result['failure_type']=type(error).__name__
    output=ROOT/'docs/release-deployment/qualification'
    raw=output/'egress-native.json'; raw.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    passed=passed and before==hashes()
    receipt={'status':'LOCAL_NETWORK_EXECUTED' if passed else 'FAILED','files':hashes(),
        'source_unchanged_during_test':before==hashes(),
        'logs':{raw.relative_to(ROOT).as_posix():hashlib.sha256(raw.read_bytes()).hexdigest()},
        'scope':'Public HEAD through real CONNECT proxy; normal TLS verification; no cloud credentials',
        'container_execution':'NOT_RUN','cloud_resource_acceptance':'NOT_RUN',
        'independent_verification':'NOT_RUN','certification':'NOT_CERTIFIED'}
    (output/'egress-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2)); print(receipt['status'])
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
