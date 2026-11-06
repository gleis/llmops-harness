"""Exercise real HTTP/LiteLLM transport with a deterministic local Ollama fixture.

This validates wiring, budget rejection, metrics and eval exit status, not model quality.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class OllamaFixture(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        text = 'Paris 5 print Hello Kubernetes OK'
        data = json.dumps({'model': body['model'], 'response': text,
                           'created_at': '2026-01-01T00:00:00Z', 'done': True,
                           'done_reason': 'stop', 'prompt_eval_count': 8,
                           'eval_count': 6, 'total_duration': 1000000}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    return urlopen(Request(url, data=body, headers={'Content-Type': 'application/json'}), timeout=10)


def main():
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), OllamaFixture)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = dict(os.environ, PYTHONPATH=str(Path('src').resolve()), OLLAMA_API_BASE=f'http://127.0.0.1:{fixture.server_port}',
               OLLAMA_BASE_URL=f'http://127.0.0.1:{fixture.server_port}',
               OTEL_SDK_DISABLED='true', DO_NOT_TRACK='true', LITELLM_LOCAL_MODEL_COST_MAP='true')
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'llmops_harness.server:app',
                                    '--host', '127.0.0.1', '--port', str(port)], env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    with request(base+'/health') as response:
                        assert json.load(response)['status'] == 'ok'
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError('harness exited before readiness')
                    time.sleep(.1)
            else:
                raise RuntimeError('harness readiness timed out')
            payload = {'provider': 'ollama', 'model': 'llama3.2', 'prompt': 'Say hi.'}
            with request(base+'/v1/complete', payload) as response:
                result = json.load(response)
                assert result['text'] and result['output_tokens'] == 6, result
            try:
                request(base+'/v1/complete', dict(payload, max_tokens=999999))
            except HTTPError as error:
                assert error.code == 429, error.code
            else:
                raise AssertionError('oversized request was accepted')
            with request(base+'/metrics') as response:
                assert b'llm_requests_total' in response.read()
            subprocess.run(['bash', 'scripts/smoke.sh'], env=dict(env, URL=base+'/v1/complete'), check=True)
            with tempfile.TemporaryDirectory() as output:
                subprocess.run([sys.executable, '-m', 'llmops_harness.evals', '--suite',
                                'evals/suites/basic.yaml', '--out', output], env=env, check=True)
                reports = list(Path(output).glob('*.json'))
                assert len(reports) == 1
                assert json.loads(reports[0].read_text())['summary']['passed'] == 5
            print('Protocol smoke passed: HTTP completion, budget 429, metrics, shell smoke, 5 eval cases')
        except BaseException:
            log.seek(0)
            print(log.read(), file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            fixture.shutdown()


if __name__ == '__main__':
    main()
