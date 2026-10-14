import socket
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import russian_proxy as relay
import transport

class RelayTests(unittest.TestCase):
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
    self.assertEqual(err.exception.code,405)
    with socket.create_connection(server.server_address,timeout=3) as stream:
     stream.sendall(b'CONNECT evil.example:443 HTTP/1.1\r\nHost: evil.example:443\r\n\r\n')
     self.assertIn(b' 403 ',stream.recv(1024))
  finally:server.shutdown();server.server_close();thread.join(3)

if __name__=='__main__':unittest.main()
