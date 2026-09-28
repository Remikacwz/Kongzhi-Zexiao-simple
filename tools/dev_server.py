"""本地开发服务器：静态文件 + 代理 /api 到本地后端。
用法: python tools/dev_server.py   （默认 http://127.0.0.1:8123）
"""
import http.server
import os
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.environ.get('DEV_API', 'http://127.0.0.1:8124')
PORT = int(os.environ.get('DEV_PORT', '8123'))
HOST = os.environ.get('DEV_HOST', '0.0.0.0')


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, fmt, *args):
        pass

    def _proxy(self):
        body = None
        if self.headers.get('Content-Length'):
            body = self.rfile.read(int(self.headers['Content-Length']))
        req = urllib.request.Request(API + self.path, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() not in ('host', 'content-length', 'connection', 'accept-encoding'):
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                self.send_response(res.status)
                for key, value in res.headers.items():
                    if key.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                        self.send_header(key, value)
                data = res.read()
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            msg = ('{"code":1,"msg":"proxy error: %s"}' % exc).encode()
            self.send_response(502)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._proxy()
        return super().do_GET()

    def do_POST(self):
        return self._proxy()

    def do_PUT(self):
        return self._proxy()

    def do_PATCH(self):
        return self._proxy()

    def do_DELETE(self):
        return self._proxy()


if __name__ == '__main__':
    os.chdir(ROOT)
    http.server.ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
