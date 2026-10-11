import os
import unittest
from unittest.mock import patch

import httpx

from chatbreez_mcp import server


class ChatBreezMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []

        def handle_request(request):
            self.requests.append(request)
            if request.url.path.endswith("/connection-state/support"):
                return httpx.Response(
                    200,
                    json={"instance": {"instanceName": "support", "state": "open"}},
                )
            return httpx.Response(200, json={"success": True})

        self.request_handler = handle_request
        real_async_client = httpx.AsyncClient

        def client_factory(**kwargs):
            return real_async_client(
                transport=httpx.MockTransport(self.request_handler),
                **kwargs,
            )

        client_patch = patch.object(server.httpx, "AsyncClient", client_factory)
        client_patch.start()
        self.addCleanup(client_patch.stop)

        env_patch = patch.dict(os.environ, {server.API_KEY_ENV_VAR: "test-secret"})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    async def test_checks_status_then_sends_with_documented_request_shape(self):
        result = await server._send_chatbreez_message(
            "support", "254700000000", "Hello there"
        )

        self.assertIn("Message accepted", result)
        self.assertEqual([request.method for request in self.requests], ["GET", "POST"])
        self.assertEqual(
            self.requests[0].url.path,
            "/whatsapp/connection-state/support",
        )
        self.assertEqual(self.requests[1].url.path, "/whatsapp/send-text/support")
        for request in self.requests:
            self.assertEqual(request.headers["X-API-Key"], "test-secret")
        self.assertEqual(
            self.requests[1].read(),
            b'{"recipient":"254700000000","text":"Hello there"}',
        )
        self.assertNotIn("test-secret", result)

    async def test_does_not_send_when_instance_is_not_connected(self):
        def handle_request(request):
            self.requests.append(request)
            return httpx.Response(
                200,
                json={"instance": {"instanceName": "support", "state": "close"}},
            )

        self.request_handler = handle_request

        with self.assertRaisesRegex(RuntimeError, "not connected"):
            await server._send_chatbreez_message(
                "support", "254700000000", "Hello there"
            )

        self.assertEqual([request.method for request in self.requests], ["GET"])

    async def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "CHATBREEZ_API_KEY"):
                await server._send_chatbreez_message(
                    "support", "254700000000", "Hello there"
                )

    async def test_validates_recipient_before_network_request(self):
        with self.assertRaisesRegex(ValueError, "digits only"):
            await server._send_chatbreez_message(
                "support", "+254700000000", "Hello there"
            )

        self.assertEqual(self.requests, [])

    async def test_surfaces_api_http_errors(self):
        def handle_request(request):
            self.requests.append(request)
            return httpx.Response(401, json={"detail": "unauthorized"})

        self.request_handler = handle_request

        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            await server._send_chatbreez_message(
                "support", "254700000000", "Hello there"
            )

        self.assertEqual([request.method for request in self.requests], ["GET"])


if __name__ == "__main__":
    unittest.main()
