"""Risk screen city/area selection and coordinate display."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from client import APIError

APP = str(Path(__file__).resolve().parents[1] / "app.py")
ROWS = [
    {"region_id": 1, "sigungu_name": "통영시", "area_name": "산양읍", "latitude": 34.7824, "longitude": 128.3882},
    {"region_id": 2, "sigungu_name": "통영시", "area_name": "욕지면", "latitude": 34.63702, "longitude": 128.26476},
    {"region_id": 3, "sigungu_name": "거제시", "area_name": "산양읍", "latitude": 35.125, "longitude": 127.625},
]
FARM = {"region": "통영시", "district": "산양읍", "species": "굴", "method": "가두리", "insurance": "미가입"}


def risk_app(farm=None):
    app = AppTest.from_file(APP, default_timeout=15)
    app.session_state["page"] = "risk"
    app.session_state["farm"] = dict(FARM if farm is None else farm)
    return app


class RiskCoordinatesWidgetTest(unittest.TestCase):
    def test_saved_area_is_selected_and_city_change_clears_old_coordinates(self):
        with (patch("client.fetch_coordinate_regions", return_value=ROWS),
              patch("client.fetch_region_coordinates", side_effect=lambda region_id: next(r for r in ROWS if r["region_id"] == region_id))):
            app = risk_app().run()
            self.assertEqual(app.selectbox(key="risk_sigungu").value, "통영시")
            self.assertEqual(app.selectbox(key="risk_region_id").value, 1)
            self.assertEqual([m.value for m in app.metric], ["34.782400", "128.388200"])
            app.selectbox(key="risk_sigungu").set_value("거제시").run()
            self.assertIsNone(app.selectbox(key="risk_region_id").value)
            self.assertFalse(app.metric)
            app.selectbox(key="risk_region_id").set_value(3).run()
            self.assertEqual([m.value for m in app.metric], ["35.125000", "127.625000"])
            self.assertEqual(app.session_state["farm"], FARM)
            app.selectbox(key="risk_sigungu").set_value(None).run()
            self.assertTrue(app.selectbox(key="risk_region_id").disabled)
            self.assertFalse(app.metric)
            self.assertFalse(app.exception)

    def test_unregistered_area_starts_with_no_coordinate_selection(self):
        with patch("client.fetch_coordinate_regions", return_value=ROWS), patch("client.fetch_region_coordinates") as detail:
            app = risk_app({**FARM, "district": "없는면"}).run()
            self.assertIsNone(app.selectbox(key="risk_region_id").value)
            self.assertFalse(app.metric)
            detail.assert_not_called()
            self.assertFalse(app.exception)

    def test_empty_list_and_connection_error_show_no_coordinates(self):
        for result, error in (([], None), (None, APIError("지역 목록 연결 실패"))):
            with self.subTest(error=bool(error)), patch("client.fetch_coordinate_regions", return_value=result, side_effect=error):
                app = risk_app().run()
                self.assertFalse(app.metric)
                self.assertFalse(app.exception)
                if error:
                    self.assertTrue(any(e.value == "지역 목록 연결 실패" for e in app.error))
                else:
                    self.assertTrue(any(i.value == "등록된 지역이 없습니다." for i in app.info))

    def test_detail_failure_does_not_leave_previous_coordinates_visible(self):
        with patch("client.fetch_coordinate_regions", return_value=ROWS), patch("client.fetch_region_coordinates", side_effect=[ROWS[0], APIError("좌표 조회 실패")]):
            app = risk_app().run()
            self.assertEqual(len(app.metric), 2)
            app.selectbox(key="risk_region_id").set_value(2).run()
            self.assertFalse(app.metric)
            self.assertTrue(any(e.value == "좌표 조회 실패" for e in app.error))
            self.assertFalse(app.exception)


@unittest.skipUnless(os.getenv("RUN_CUSTOMER_DB_TESTS") == "1", "Enable DB checks for UI-to-DB coordinates")
class RiskCoordinatesDatabaseTest(unittest.TestCase):
    def test_screen_selection_matches_postgresql_coordinates(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from backend.tests.support import add_coordinate_fixtures, customer_sandbox, request
        import client

        def transport(method, path, *, body=None, token=None):
            status, result, _ = request(method, path, body, token)
            if status >= 400:
                raise APIError(str(result.get("detail")))
            return result

        for cached in (client.fetch_coordinate_regions, client.fetch_region_coordinates):
            cached.clear()
            self.addCleanup(cached.clear)
        with customer_sandbox() as sandbox:
            rows = add_coordinate_fixtures(sandbox)
            farm = {**FARM, "region": rows[0]["sigungu_name"], "district": rows[0]["area_name"]}
            with patch("client._api", side_effect=transport):
                app = risk_app(farm).run()
                self.assertEqual([m.value for m in app.metric], ["35.125000", "128.500000"])
                app.selectbox(key="risk_sigungu").set_value(rows[2]["sigungu_name"]).run()
                self.assertFalse(app.metric)
                app.selectbox(key="risk_region_id").set_value(rows[2]["region_id"]).run()
                self.assertEqual([m.value for m in app.metric], ["34.654321", "127.123456"])
                self.assertEqual(app.session_state["farm"], farm)
                self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
