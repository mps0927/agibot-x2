import argparse
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from app import create_app


class SensorPage(unittest.IsolatedAsyncioTestCase):
    async def test_sensor_route_is_separate_and_does_not_take_control(self):
        args = argparse.Namespace(offline=True, allow_control=False, origin='',
                                  env_file=str(Path(__file__).parent / 'missing-fixture.env'))
        app = create_app(args)
        dashboard = app['dashboard']
        async with TestClient(TestServer(app)) as client:
            main = await client.get('/')
            main_html = await main.text()
            self.assertIn('href="/sensor"', main_html)
            self.assertNotIn('id="sensor-list"', main_html)
            self.assertIn('id="include-lidar"', main_html)
            owner = dashboard.owner
            response = await client.get('/sensor')
            self.assertEqual(response.status, 200)
            html = await response.text()
            self.assertIn('id="sensor-list"', html)
            self.assertIn('id="save-sensors"', html)
            self.assertIn('id="sensor-search"', html)
            self.assertNotIn('/static/app.js', html)
            self.assertNotIn('id="arm"', html)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(dashboard.owner, owner)
            for path in ('/static/sensor.css', '/static/sensors.js', '/api/sensors'):
                with self.subTest(path=path):
                    result = await client.get(path)
                    self.assertEqual(result.status, 200)
                    await result.read()


if __name__ == '__main__':
    unittest.main()
