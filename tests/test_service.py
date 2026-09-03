import asyncio
import importlib
import io
import json
import sys
import types
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError


class _Server:
    registered_tools = []
    http_app_options = {}

    def __init__(self, name):
        self.name = name

    def tool(self, *_args):
        def register(function):
            self.registered_tools.append(function.__name__)
            return function

        return register

    def http_app(self, **kwargs):
        self.http_app_options.update(kwargs)
        return object()


class _Mangum:
    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class GeoLookupTests(unittest.TestCase):
    def setUp(self):
        _Server.registered_tools = []
        _Server.http_app_options = {}
        self.module_patch = mock.patch.dict(
            sys.modules,
            {
                "fastmcp": types.SimpleNamespace(Server=_Server),
                "mangum": types.SimpleNamespace(Mangum=_Mangum),
            },
        )
        self.module_patch.start()
        sys.modules.pop("service.service", None)
        self.service = importlib.import_module("service.service")

    def tearDown(self):
        sys.modules.pop("service.service", None)
        self.module_patch.stop()

    def test_registers_geo_lookup_with_stateless_http_transport(self):
        self.assertIn("geo_lookup", _Server.registered_tools)
        self.assertTrue(_Server.http_app_options["stateless_http"])

    def test_forwards_tool_arguments_to_geo_api(self):
        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://api.lukach.io/geo")
            self.assertEqual(
                request.data,
                b'{"ip": "1.1.1.1", "ips": ["8.8.8.8"]}',
            )
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(timeout, 20)
            return _Response(b'{"results":[{"ip":"1.1.1.1"}],"requested_count":1}')

        with mock.patch.object(self.service, "urlopen", fake_urlopen):
            result = asyncio.run(self.service.geo_lookup("1.1.1.1", ["8.8.8.8"]))

        self.assertEqual(result["requested_count"], 1)
        self.assertEqual(result["results"][0]["ip"], "1.1.1.1")

    def test_returns_structured_error_when_geo_is_unavailable(self):
        with mock.patch.object(self.service, "urlopen", side_effect=URLError("unavailable")):
            result = asyncio.run(self.service.geo_lookup(ips=["1.1.1.1"]))

        self.assertEqual(result["error"], "geo_lookup_unavailable")
        self.assertEqual(result["message"], "unavailable")

    def test_preserves_geo_json_errors(self):
        error = HTTPError(
            "https://api.lukach.io/geo",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":"At least one IP address is required"}'),
        )

        with mock.patch.object(self.service, "urlopen", side_effect=error):
            result = asyncio.run(self.service.geo_lookup())

        self.assertEqual(result, {"error": "At least one IP address is required"})

    def test_geo_blueprint_advertises_complete_http_and_mcp_requirements(self):
        blueprint = json.loads(asyncio.run(self.service.get_api_instructions("geo")))

        self.assertEqual(blueprint["supported_http_methods"], ["GET", "POST"])
        self.assertEqual(blueprint["mcp"]["protocol_version"], "2025-06-18")
        self.assertEqual(blueprint["mcp"]["tool_name"], "geo_lookup")
        self.assertIn("original input order", blueprint["duplicate_ip_behavior"]["server_behavior"])
        self.assertEqual(
            blueprint["mcp"]["headers"]["Accept"],
            "application/json, text/event-stream",
        )


if __name__ == "__main__":
    unittest.main()