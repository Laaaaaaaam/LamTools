@echo off
chcp 65001 >nul
cd /d E:\LamTools\e2e\test-apps\ai-pipeline
echo Starting AI Chat server on http://127.0.0.1:9999
echo.
echo Click: Settings icon → fill in:
echo   API Key: sk-f58f368...
echo   Base URL: https://api.deepseek.com/v1
echo   Model: deepseek-chat
echo.
start http://127.0.0.1:9999/index.html
python -c "
import http.server, os, json, urllib.request, urllib.error, socketserver

ROOT = r'E:\LamTools\e2e\test-apps\ai-pipeline'
os.chdir(ROOT)

class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.js': 'application/javascript',
        '.css': 'text/css',
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)
    
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()
    
    def do_POST(self):
        if self.path != '/chat':
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length))
        
        key = body.get('apiKey','')
        base = (body.get('baseUrl','')).rstrip('/')
        model = body.get('model','')
        msgs = body.get('messages',[])
        mt = body.get('maxTokens',2048)
        temp = body.get('temperature',0.7)
        
        payload = json.dumps({
            'model': model, 'messages': msgs,
            'max_tokens': mt, 'temperature': temp, 'stream': True,
        }).encode()
        
        req = urllib.request.Request(f'{base}/chat/completions', data=payload, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {key}',
        })
        
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-cache')
            self.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk: break
                self.wfile.write(chunk)
                self.wfile.flush()
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._cors()
            self.end_headers()
            self.wfile.write(e.read())
    
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')

class ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

s = ReusableServer(('127.0.0.1', 9999), H)
print('Server ready.')
s.serve_forever()
"
pause
