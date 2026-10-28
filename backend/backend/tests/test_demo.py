"""Demo routes and temperature calculations, without DB access."""
from copy import deepcopy
from datetime import date, timedelta
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import demo


class DemoTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(demo.router)
        self.client = TestClient(app)
        self.today = date(2026, 10, 28)
        self.sea = {
            "region": "test", "today": {"temp": 20}, "alert": None,
            "roms": [{"day": self.today + timedelta(days=i), "max": 20, "mean": 19, "min": 18,
                      "value": 20, "stage": 0, "streak28": 0} for i in range(7)],
            "om": [{"day": self.today + timedelta(days=i), "max": 20, "mean": 19, "min": 18,
                    "value": 20, "stage": 0, "streak28": 0} for i in range(7, 21)],
            "stage": {"level": 0}, "stage_extended": {"level": 0}, "max7": {"temp": 20},
        }

    def test_four_screens_reuse_originals_with_demo_bootstrap(self):
        for name in demo.SCREENS:
            response = self.client.get('/demo/' + name)
            self.assertEqual(response.status_code, 200)
            self.assertIn('/demo/demo.js', response.text)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            if name != 'consult_status.html':
                self.assertIn('data = window.DemoSimulation.adjustRegions(data);', response.text)
            self.assertNotIn('/demo/demo.js', (demo.ROOT / name).read_text(encoding='utf-8'))

    def test_static_assets_are_allowlisted(self):
        for name in ('shell.js', 'shell.css', 'demo.js', 'demo.css'):
            self.assertEqual(self.client.get('/demo/' + name).status_code, 200)
        for name in ('not-a-screen.html', 'backend.py', 'credentials.txt'):
            self.assertEqual(self.client.get('/demo/' + name).status_code, 404)

    def test_write_routes_are_blocked(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(self.client.request(method, '/demo/api/consult/logs').status_code, 403)

    def test_invalid_offsets_never_read_database(self):
        with patch.object(demo.detail, 'q_one') as query:
            for value in ('-1', '15.5', '0.25', 'bad', 'nan', 'inf'):
                self.assertEqual(self.client.get('/demo/api/households/1/detail', params={'offset': value}).status_code, 422)
            query.assert_not_called()

    def test_offset_defaults_to_zero(self):
        with patch.object(demo.detail, 'q_one', return_value=None):
            self.assertEqual(self.client.get('/demo/api/households/1/detail').status_code, 404)

    def test_offset_recalculates_all_periods_and_preserves_original(self):
        original = deepcopy(self.sea)
        adjusted = demo.adjust_sea(self.sea, 8, self.today)
        self.assertEqual(self.sea, original)
        self.assertEqual(adjusted['today']['temp'], 28)
        self.assertEqual(adjusted['roms'][0]['max'], 28)
        self.assertEqual(adjusted['om'][-1]['value'], 28)
        self.assertEqual(adjusted['stage']['level'], 3)
        self.assertEqual(adjusted['stage']['d'], 2)
        self.assertEqual(adjusted['max7']['temp'], 28)
        self.assertEqual(adjusted['om'][0]['streak28'], 3)
        self.assertIsNone(adjusted['alert'])
        self.assertEqual(demo.adjust_sea(self.sea, 0, self.today), original)

    def test_missing_temperatures_remain_missing(self):
        self.sea['today']['temp'] = None
        self.sea['roms'] = []
        self.sea['om'] = []
        adjusted = demo.adjust_sea(self.sea, 5, self.today)
        self.assertIsNone(adjusted['today']['temp'])
        self.assertIsNone(adjusted['max7'])
        self.assertIsNone(adjusted['stage']['level'])

    def test_detail_reuses_adjusted_sea_for_cards_and_guidance(self):
        household = {key: None for key in ('household_name', 'owner_name', 'fishery_type', 'license_number',
                                         'sigungu_name', 'area_name', 'lat', 'lon', 'phone_number')}
        household['household_id'] = 1
        with (patch.object(demo.detail, 'today_kst', return_value=self.today),
              patch.object(demo.detail, 'q_one', return_value=household),
              patch.object(demo.detail, 'q_all', return_value=[]),
              patch.object(demo.detail, 'build_sea', return_value=self.sea),
              patch.object(demo.detail, 'build_cards', return_value=([], 'test')) as cards,
              patch.object(demo.detail, 'check_guide', return_value='test'),
              patch.object(demo.detail, 'talking_points', return_value=[]) as checks,
              patch.object(demo.detail, 'example_script', return_value='test') as script,
              patch.object(demo.detail, 'load_consult', return_value={})):
            response = self.client.get('/demo/api/households/1/detail?offset=8')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stage']['level'], 3)
        self.assertEqual(cards.call_args.args[2]['today']['temp'], 28)
        self.assertEqual(checks.call_args.args[2], 3)
        self.assertEqual(script.call_args.args[3]['max7']['temp'], 28)


if __name__ == '__main__':
    unittest.main()
