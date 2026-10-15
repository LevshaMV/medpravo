"""Loopback-only HTTPS CONNECT relay for approved public legal sources.

On a Russian VPS it is reachable only through an authenticated SSH tunnel.
It never decrypts source TLS and cannot reach private addresses or other hosts.
"""
import argparse
import ipaddress
import http.client
import json
import os
from pathlib import Path
import select
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import network

ROOT=Path(__file__).resolve().parent
MAX_BYTES=24*1024*1024

def destination(authority,domains):
    value=urllib.parse.urlsplit('//'+authority)
    host=(value.hostname or '').lower().rstrip('.')
    if value.username or value.password or value.path or value.query or value.fragment or value.port!=443:
        raise ValueError('HTTPS source on port 443 required')
    if not any(host==d or host.endswith('.'+d) for d in domains):raise ValueError('Source is not approved')
    return host,443

def open_public(host,port,index=0):
    if index and os.name=='nt':return network.connect_direct(index,(host,port),12)
    last=None
    for _,_,_,_,address in socket.getaddrinfo(host,port,socket.AF_INET,socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[0]).is_global:raise ValueError('Private network is forbidden')
        stream=socket.socket(socket.AF_INET,socket.SOCK_STREAM);stream.settimeout(12)
        try:stream.connect(address);return stream
        except OSError as exc:last=exc;stream.close()
    raise last or OSError('No public IPv4 address')

class RelayHandler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def do_CONNECT(self):
        remote=None;acquired=False;established=False
        self.close_connection=True
        try:
            host,port=destination(self.path,self.server.domains)
            acquired=self.server.slots.acquire(blocking=False)
            if not acquired:self.send_error(503);return
            remote=open_public(host,port,self.server.interface)
            self.send_response(200,'Connection established');self.end_headers();self.wfile.flush();established=True
            self.connection.settimeout(12)
            transferred=0;deadline=time.monotonic()+90
            while time.monotonic()<deadline and transferred<MAX_BYTES:
                ready,_,_=select.select([self.connection,remote],[],[],12)
                if not ready:break
                for source in ready:
                    data=source.recv(65536)
                    if not data:return
                    transferred+=len(data)
                    if transferred>MAX_BYTES:return
                    (remote if source is self.connection else self.connection).sendall(data)
        except ValueError:
            if not established:self.send_error(403,'Source is not approved')
        except (OSError,TimeoutError):
            if not established:self.send_error(502,'Source connection failed')
        finally:
            if remote:remote.close()
            if acquired:self.server.slots.release()
    def do_GET(self):
        self.close_connection=True
        if self.path=='/health':
            body=b'{"service":"medpravo-relay","http_sources":true}'
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        acquired=False;remote=None
        try:
            u=urllib.parse.urlsplit(self.path);host=(u.hostname or '').lower().rstrip('.')
            if u.scheme!='http' or u.username or u.password or u.fragment or u.port not in (None,80) or not any(host==d or host.endswith('.'+d) for d in self.server.domains):
                self.send_error(403,'Public source HTTP URL required');return
            acquired=self.server.slots.acquire(blocking=False)
            if not acquired:self.send_error(503);return
            remote=http.client.HTTPConnection(host,80,timeout=12)
            remote._create_connection=lambda address,timeout,source_address=None:open_public(host,80,self.server.interface)
            headers={key:self.headers[key] for key in ('User-Agent','Accept','Accept-Encoding','If-None-Match','If-Modified-Since') if self.headers.get(key)}
            headers['Connection']='close'
            remote.request('GET',urllib.parse.urlunsplit(('','',u.path or '/',u.query,'')),headers=headers)
            response=remote.getresponse()
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:self.send_error(502,'Source response too large');return
            self.send_response(response.status)
            for key in ('Content-Type','Content-Encoding','ETag','Last-Modified','Location'):
                if response.getheader(key):self.send_header(key,response.getheader(key))
            self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers();self.wfile.write(raw)
        except (ValueError,OSError,http.client.HTTPException):self.send_error(502,'Source connection failed')
        finally:
            if remote:remote.close()
            if acquired:self.server.slots.release()
    def log_message(self,*args):pass

def make_server(port=8118,interface=0):
    sources=json.loads((ROOT/'sources.json').read_text(encoding='utf-8-sig'))
    server=ThreadingHTTPServer(('127.0.0.1',port),RelayHandler)
    server.domains={d for s in sources for d in s['allowed_domains']}
    server.slots=threading.BoundedSemaphore(8);server.interface=interface
    return server

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8118)
    parser.add_argument('--interface',type=int,default=0)
    args=parser.parse_args()
    with make_server(args.port,args.interface) as server:
        print('MedPravo relay listening on loopback',flush=True)
        server.serve_forever()

if __name__=='__main__':main()
