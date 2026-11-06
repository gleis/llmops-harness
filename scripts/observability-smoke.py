"""Verify real harness metrics and OTLP traces through the rebuilt review stack."""
import json
from datetime import datetime, timedelta, timezone
import os
import runpy
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get(url):
    with urlopen(url, timeout=5) as response:
        return response.read()


def eventually(check, label):
    last = None
    for _ in range(90):
        try:
            if check():
                print(label + ': passed', flush=True)
                return
        except Exception as error:
            last = error
        time.sleep(1)
    raise AssertionError(f'{label} failed: {last}')


def main():
    fixture_type = runpy.run_path('scripts/protocol-smoke.py')['OllamaFixture']
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), fixture_type)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    env = dict(os.environ, OLLAMA_API_BASE=f'http://127.0.0.1:{fixture.server_port}',
               OTEL_EXPORTER_OTLP_ENDPOINT='http://127.0.0.1:4318',
               OTEL_BSP_SCHEDULE_DELAY='500', DO_NOT_TRACK='true',
               LITELLM_LOCAL_MODEL_COST_MAP='true')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'llmops_harness.server:app',
                                '--host', '0.0.0.0', '--port', '8000'], env=env)
    try:
        eventually(lambda: json.loads(get('http://127.0.0.1:8000/health'))['status'] == 'ok', 'harness ready')
        eventually(lambda: bool(get('http://127.0.0.1:9090/-/ready')), 'Prometheus ready')
        eventually(lambda: bool(get('http://127.0.0.1:16686/')), 'Jaeger UI assets')
        eventually(lambda: b'<html' in get('http://127.0.0.1:9090/').lower(), 'Prometheus UI assets')
        body = json.dumps({'provider': 'ollama', 'model': 'llama3.2', 'prompt': 'Say hi.'}).encode()
        with urlopen(Request('http://127.0.0.1:8000/v1/complete', data=body,
                             headers={'Content-Type': 'application/json'}), timeout=15) as response:
            assert json.load(response)['output_tokens'] == 6
        query = 'http://127.0.0.1:9090/api/v1/query?' + urlencode({'query': 'llm_requests_total{status="ok"}'})
        eventually(lambda: any(float(row['value'][1]) >= 1 for row in json.loads(get(query))['data']['result']), 'actual harness metric scraped')
        now = datetime.now(timezone.utc)
        traces = 'http://127.0.0.1:16686/api/v3/traces?' + urlencode({
            'query.serviceName': 'llmops-harness',
            'query.startTimeMin': (now-timedelta(minutes=5)).isoformat(),
            'query.startTimeMax': (now+timedelta(minutes=5)).isoformat(),
        })
        def has_harness_span():
            result = json.loads(get(traces))['result']
            return any(span['name'] == 'llm.complete'
                       for resource in result.get('resourceSpans', [])
                       for scope in resource.get('scopeSpans', [])
                       for span in scope.get('spans', []))
        eventually(has_harness_span, 'actual OTLP trace ingested and queried')
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
