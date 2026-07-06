"""
AI 对话服务器
- 使用 Python http.server 提供静态文件服务和 SSE 接口
- /chat 端点接收用户消息，将消息反转后逐字流式返回
"""
import http.server
import json
import time
import os

PORT = 8000

class ChatHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，支持 SSE 流式响应"""

    def do_POST(self):
        """处理 POST 请求"""
        if self.path == '/chat':
            # 读取请求体
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)
            user_message = data.get('message', '')

            # 反转消息
            reversed_message = user_message[::-1]

            # 设置 SSE 响应头
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            # 逐字流式发送反转后的消息
            for char in reversed_message:
                # 构造 SSE 数据
                sse_data = json.dumps({'token': char})
                self.wfile.write(f"data: {sse_data}\n\n".encode('utf-8'))
                self.wfile.flush()
                time.sleep(0.1)  # 模拟流式延迟

            # 发送结束标记
            self.wfile.write(f"data: {json.dumps({'done': True})}\n\n".encode('utf-8'))
            self.wfile.flush()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """处理 GET 请求 - 提供静态文件"""
        # 如果访问根路径，重定向到 chat.html
        if self.path == '/':
            self.path = '/chat.html'
        return super().do_GET()


if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = http.server.HTTPServer(server_address, ChatHandler)
    print(f"🚀 服务器启动: http://localhost:{PORT}")
    print(f"📄 打开浏览器访问 http://localhost:{PORT}")
    httpd.serve_forever()
