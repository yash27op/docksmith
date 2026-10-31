import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app import Handler
from core import ModelError, demo, generate, lint, parse_output, validate_request


class CoreTests(unittest.TestCase):
    def test_validation(self):
        for bad in (None, [], {}, {"description": 5}, {"description": "x" * 8001}):
            with self.assertRaises(ValueError):
                validate_request(bad)

    def test_output_contract(self):
        for raw in ('no json', '[]', '{}', '{"dockerfile": 1}'):
            with self.assertRaises(ModelError):
                parse_output(raw)

    def test_linter_runtime_stage(self):
        warnings = lint('FROM python:latest AS build\nUSER 1000\nFROM python:3.13-slim\nCMD python app.py')
        self.assertEqual(len(warnings), 3)
        self.assertEqual(lint(demo()['dockerfile']), [])

    def test_ollama_transport(self):
        captured = []
        class FakeOllama(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                result = demo()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'done': True, 'response': json.dumps(result)}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with patch.dict(os.environ, {'OLLAMA_URL': f'http://127.0.0.1:{server.server_port}', 'OLLAMA_MODEL': 'test-model'}):
                result = generate({'description': 'FastAPI app'})
            self.assertFalse(result['demo'])
            self.assertEqual(captured[0][0], '/api/generate')
            self.assertFalse(captured[0][1]['stream'])
            self.assertEqual(captured[0][1]['model'], 'test-model')
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_connection_error(self):
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(ModelError):
                generate({'description': 'app'})


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def post(self, route, value):
        return urllib.request.urlopen(urllib.request.Request(self.url + route, data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'}))

    def test_demo_download(self):
        with self.post('/api/demo', {}) as response:
            result = json.load(response)
        self.assertTrue(result['demo'])
        with self.post('/api/download', result) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(set(archive.namelist()), {'Dockerfile', '.dockerignore', 'NOTES.txt'})
                self.assertEqual(archive.read('Dockerfile').decode(), result['dockerfile'])

    def test_reject_bad_download(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/api/download', {})
        self.assertEqual(caught.exception.code, 400)

    def test_no_static_traversal(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.url + '/core.py')
        self.assertEqual(caught.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
