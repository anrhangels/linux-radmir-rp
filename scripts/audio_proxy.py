"""Loopback-only diagnostic proxy, restricted to Radmir music downloads."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,urlunsplit,unquote_to_bytes,quote
from urllib.request import Request,urlopen,ProxyHandler,build_opener
from urllib.error import HTTPError

def normalized(url):
    p=urlsplit(url)
    if p.scheme!='http' or p.hostname!='music.radmir.online' or p.port not in (None,80) or p.username or p.password:
        raise ValueError('Only Radmir music HTTP URLs are allowed')
    try: wire_path=p.path.encode('latin1')
    except UnicodeEncodeError: wire_path=p.path.encode('utf-8')
    raw=unquote_to_bytes(wire_path)
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError: text=raw.decode('cp1251')
    return urlunsplit(('http','music.radmir.online',quote(text,safe='/$-_.~'),p.query,''))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        try: target=normalized(self.path)
        except (ValueError,UnicodeError): self.send_error(403);return
        request=Request(target,headers={k:v for k,v in self.headers.items() if k.lower() in ('range','user-agent','accept','icy-metadata')})
        try: response=build_opener(ProxyHandler({})).open(request,timeout=15)
        except HTTPError as exc: response=exc
        except OSError: self.send_error(502);return
        with response:
            self.send_response(response.status)
            for k,v in response.headers.items():
                if k.lower() in ('content-type','content-length','content-range','accept-ranges'):self.send_header(k,v)
            self.end_headers()
            try:
                while chunk:=response.read(65536): self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError): pass

def serve():
    server=ThreadingHTTPServer(('127.0.0.1',18764),Handler)
    server.daemon_threads=True
    return server

# The game-session proxy also forwards unrelated requests unchanged, so the
# launcher can use its usual services while Wine's proxy setting is active.
import socket
import select
class SessionHandler(Handler):
    def do_CONNECT(self):
        try:
            host,port=self.path.rsplit(':',1)
            if int(port)!=443: self.send_error(403);return
            upstream=socket.create_connection((host,443),timeout=15)
        except (OSError,ValueError): self.send_error(502);return
        self.send_response(200);self.end_headers()
        with upstream:
            self.connection.settimeout(None);upstream.settimeout(None)
            while True:
                ready,_,_=select.select([self.connection,upstream],[],[],60)
                if not ready:return
                for src in ready:
                    try:
                        chunk=src.recv(65536)
                        if not chunk:return
                        (upstream if src is self.connection else self.connection).sendall(chunk)
                    except OSError:return
    def do_GET(self):
        p=urlsplit(self.path)
        if p.hostname=='music.radmir.online':return super().do_GET()
        if p.scheme!='http' or not p.hostname:self.send_error(403);return
        request=Request(self.path,headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','proxy-connection','proxy-authorization')})
        try:response=build_opener(ProxyHandler({})).open(request,timeout=20)
        except HTTPError as exc:response=exc
        except OSError:self.send_error(502);return
        with response:
            self.send_response(response.status)
            for k,v in response.headers.items():
                if k.lower() not in ('transfer-encoding','connection','keep-alive','proxy-authenticate'):self.send_header(k,v)
            self.end_headers()
            try:
                while chunk:=response.read(65536):self.wfile.write(chunk)
            except (OSError,ConnectionError):pass
