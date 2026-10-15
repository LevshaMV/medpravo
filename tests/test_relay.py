import socket
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import russian_proxy as relay
import transport
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

class RelayTests(unittest.TestCase):
 def test_https_proxy_does_not_break_plain_http_sources(self):
  class Page(BaseHTTPRequestHandler):
   def do_GET(self):
    self.send_response(200);self.end_headers();self.wfile.write(b'legal catalog')
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Page)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   # Empty-string HTTP proxies cause urllib to fail with "no host given".
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':transport.relay_url('http://127.0.0.1:8118')}))
   with opener.open('http://127.0.0.1:'+str(server.server_port),timeout=3) as response:
    self.assertEqual(response.read(),b'legal catalog')
  finally:server.shutdown();server.server_close();thread.join(3)
 def test_only_approved_https_authorities_are_allowed(self):
  self.assertEqual(relay.destination('oms-kaluga.ru:443',{'oms-kaluga.ru'}),('oms-kaluga.ru',443))
  for target in ['evil.example:443','oms-kaluga.ru.evil.example:443','owner:secret@oms-kaluga.ru:443','oms-kaluga.ru:22','oms-kaluga.ru:443/private','127.0.0.1:443']:
   with self.subTest(target=target),self.assertRaises(ValueError):relay.destination(target,{'oms-kaluga.ru'})
 def test_source_dns_cannot_point_at_a_private_address(self):
  with patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,0,'',('127.0.0.1',443))]):
   with self.assertRaises(ValueError):relay.open_public('oms-kaluga.ru',443)
 def test_collector_rejects_open_remote_proxies_and_credentials(self):
  self.assertEqual(transport.relay_url('http://127.0.0.1:8118'),'http://127.0.0.1:8118')
  for value in ['http://public.example:8118','http://user:key@127.0.0.1:8118','https://127.0.0.1:8118','http://127.0.0.1:22','http://127.0.0.1:8118/?key=secret']:
   with self.subTest(value=value),self.assertRaises(ValueError):transport.relay_url(value)
 def test_http_requests_and_non_sources_do_not_open_upstream_sockets(self):
  server=relay.make_server(port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch.object(relay,'open_public',side_effect=AssertionError('Must not connect')):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with self.assertRaises(urllib.error.HTTPError) as err:opener.open('http://127.0.0.1:'+str(server.server_port)+'/')
    self.assertEqual(err.exception.code,403)
    with socket.create_connection(server.server_address,timeout=3) as stream:
     stream.sendall(b'CONNECT evil.example:443 HTTP/1.1\r\nHost: evil.example:443\r\n\r\n')
     self.assertIn(b' 403 ',stream.recv(1024))
  finally:server.shutdown();server.server_close();thread.join(3)

 def test_http_proxy_rejects_credentials_private_hosts_and_other_ports(self):
  server=relay.make_server(port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch.object(relay,'open_public',side_effect=AssertionError('Must not connect')):
    for target in ['http://127.0.0.1/','http://pravo.gov.ru:22/','http://owner:secret@pravo.gov.ru/','http://pravo.gov.ru.evil.example/']:
     with socket.create_connection(server.server_address,timeout=3) as stream:
      stream.sendall(('GET '+target+' HTTP/1.1\r\nHost: ignored\r\n\r\n').encode())
      self.assertIn(b' 403 ',stream.recv(1024))
   transport.RELAY_HTTP.clear()
   self.assertEqual(set(transport.proxy_protocols('http://127.0.0.1:'+str(server.server_port))),{'http','https'})
  finally:server.shutdown();server.server_close();thread.join(3)

 def test_http_source_response_is_forwarded_without_cookies_or_authentication(self):
  seen={}
  class Page(BaseHTTPRequestHandler):
   def do_GET(self):
    seen.update(path=self.path,headers=dict(self.headers))
    self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b'official act')
   def log_message(self,*args):pass
  upstream=ThreadingHTTPServer(('127.0.0.1',0),Page)
  proxy=relay.make_server(port=0)
  threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (upstream,proxy)]
  for t in threads:t.start()
  try:
   with patch.object(relay,'open_public',side_effect=lambda *a:socket.create_connection(upstream.server_address,timeout=3)) as opened:
    with socket.create_connection(proxy.server_address,timeout=3) as stream:
     stream.sendall(b'GET http://www.pravo.gov.ru/?day=15 HTTP/1.1\r\nHost: ignored\r\nAuthorization: secret\r\nCookie: secret\r\nConnection: close\r\n\r\n')
     parts=[]
     while block:=stream.recv(4096):parts.append(block)
    self.assertIn(b'official act',b''.join(parts));opened.assert_called_once_with('www.pravo.gov.ru',80,0)
   self.assertEqual(seen['path'],'/?day=15');self.assertNotIn('Cookie',seen['headers']);self.assertNotIn('Authorization',seen['headers'])
  finally:
   for s in (upstream,proxy):s.shutdown();s.server_close()
   for t in threads:t.join(3)

if __name__=='__main__':unittest.main()
