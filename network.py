"""Optional Windows per-socket routing; does not modify VPN or system routes."""
import http.client
import ipaddress
import socket
import struct

def connect_direct(index,address,timeout,source_address=None):
    last=None
    for _,_,_,_,target in socket.getaddrinfo(address[0],address[1],socket.AF_INET,socket.SOCK_STREAM):
        if not ipaddress.ip_address(target[0]).is_global:
            raise OSError('Прямое подключение разрешено только к публичным адресам')
        sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.IPPROTO_IP,31,struct.pack('!I',index))
            sock.settimeout(timeout)
            if source_address:sock.bind(source_address)
            sock.connect(target)
            return sock
        except OSError as exc:last=exc;sock.close()
    raise last or OSError('Нет IPv4-адреса источника')

class DirectHTTPConnection(http.client.HTTPConnection):
    def __init__(self,*args,interface_index,**kwargs):
        super().__init__(*args,**kwargs)
        self._create_connection=lambda address,timeout,source_address=None:connect_direct(interface_index,address,timeout,source_address)

class DirectHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,*args,interface_index,**kwargs):
        super().__init__(*args,**kwargs)
        self._create_connection=lambda address,timeout,source_address=None:connect_direct(interface_index,address,timeout,source_address)
