"""Species choice buttons and opt-in UI-to-DB account persistence."""
from datetime import date
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from client import APIError, local_farm, save_farm
from test_guest_flow import CATALOG

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class SpeciesWidgetTest(unittest.TestCase):
    def test_catalogue_refresh_replaces_an_old_abalone_only_list(self):
        old = {"regions": CATALOG["regions"], "species": [{"species_id": 9, "species_name": "전복"}]}
        added = ["가숭어", "말쥐치", "참쥐치", "볼락", "점농어", "능성어", "방어", "미더덕", "오만둥이"]
        current = {"regions": CATALOG["regions"], "species": CATALOG["species"] +
                   [{"species_id": i + 100, "species_name": name} for i, name in enumerate(added)]}
        with (patch("client.fetch_regions", return_value=(["거제시"], False)),
              patch("client.fetch_registration_catalog", return_value=old) as fetch):
            app = AppTest.from_file(APP).run()
            app.button(key="start_button").click().run()
            self.assertEqual(app.selectbox(key="farm_species").options, ["전복"])
            app.session_state["registration_catalog"] = old  # old sessions may still have this snapshot
            fetch.return_value = current
            app.run()
            self.assertTrue(set(added).issubset(app.selectbox(key="farm_species").options))
            app.selectbox(key="farm_species").select("미더덕").run()
            app.run()
            self.assertEqual(app.selectbox(key="farm_species").value, "미더덕")
            self.assertFalse(app.exception)

    def test_abalone_is_grouped_and_buttons_reset_when_species_changes(self):
        with (patch("client.fetch_regions", return_value=(["거제시"], False)),
              patch("client.fetch_registration_catalog", return_value=CATALOG)):
            app = AppTest.from_file(APP).run()
            app.button(key="start_button").click().run()
            self.assertEqual(app.selectbox(key="farm_species").options.count("전복"), 1)
            self.assertNotIn("전복(육상)", app.selectbox(key="farm_species").options)
            self.assertNotIn("farm_abalone_kind", [s.key for s in app.segmented_control])
            app.selectbox(key="farm_species").select("전복").run()
            self.assertIsNone(app.segmented_control(key="farm_abalone_kind").value)
            app.segmented_control(key="farm_abalone_kind").set_value("해상").run()
            self.assertEqual(app.session_state["farm_method"], "가두리")
            app.selectbox(key="farm_species").select("조피볼락 (우럭)").run()
            self.assertNotIn("farm_abalone_kind", [s.key for s in app.segmented_control])
            app.selectbox(key="farm_species").select("전복").run()
            self.assertIsNone(app.segmented_control(key="farm_abalone_kind").value)
            self.assertFalse(app.exception)

    def test_missing_kind_and_failed_save_do_not_finish_registration(self):
        with (patch("client.fetch_regions", return_value=(["거제시"], False)),
              patch("client.fetch_registration_catalog", return_value=CATALOG),
              patch("client.save_farm", side_effect=APIError("저장 실패")) as save):
            app = AppTest.from_file(APP).run()
            app.button(key="start_button").click().run()
            app.selectbox(key="farm_region").select("거제시").run()
            app.selectbox(key="farm_district").select("둔덕면").run()
            app.selectbox(key="farm_species").select("전복").run()
            app.session_state["farm_insurance"] = "미가입"
            next(b for b in app.button if b.label == "등록하기").click().run()
            save.assert_not_called()
            self.assertTrue(any("전복 구분" in e.value for e in app.error))
            app.segmented_control(key="farm_abalone_kind").set_value("육상").run()
            next(b for b in app.button if b.label == "등록하기").click().run()
            self.assertEqual(save.call_args.args[0]["abalone_kind"], "육상")
            self.assertEqual(app.session_state["page"], "register")
            self.assertTrue(app.error)
            self.assertFalse(app.exception)


class SpeciesClientTest(unittest.TestCase):
    def test_button_choice_resolves_to_catalogue_species_id_and_restores(self):
        for kind, species_id, method in (("육상", 2, "육상"), ("해상", 3, "가두리")):
            with self.subTest(kind=kind), patch("client.fetch_registration_catalog", return_value=CATALOG), patch("client._api") as api:
                farm = {"region": "거제시", "district": "둔덕면", "species": "전복", "abalone_kind": kind,
                        "method": method, "insurance": "미가입"}
                save_farm(farm)
                body = api.call_args.kwargs["body"]
                self.assertEqual(body["species_ids"], [species_id])
                self.assertEqual(set(body), {"species_ids", "region_id", "farming_method", "insurance_status"})
                restored = local_farm({"sigungu_name": "거제시", "town_name": "둔덕면", **body})
                self.assertEqual(restored["species"], "전복")
                self.assertEqual(restored["abalone_kind"], kind)


@unittest.skipUnless(os.getenv("RUN_CUSTOMER_DB_TESTS") == "1", "Enable DB checks for UI/account flow")
class SpeciesAccountRoundTripTest(unittest.TestCase):
    def test_ui_choice_signup_relogin_and_edit_match_species_table(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from backend.species_catalog import seed_abalone_species
        from backend.tests.support import RewrittenConnection, customer_sandbox, request
        import client

        def transport(method, path, *, body=None, token=None):
            status, result, _ = request(method, path, body, token, {"X-CSRF-Protection": "1"})
            if status >= 400:
                raise APIError(str(result.get("detail")))
            return result

        for cached in (client.fetch_registration_catalog, client.fetch_coordinate_regions, client.fetch_region_coordinates):
            cached.clear()
            self.addCleanup(cached.clear)
        with customer_sandbox() as sandbox:
            seed_abalone_species(RewrittenConnection(sandbox.connection, sandbox.schema))

            def stored_species(farm_id):
                return sandbox.connection.execute(f"""
                    SELECT s.species_name FROM {sandbox.schema}.farm_species fs
                    JOIN {sandbox.schema}.species s USING(species_id) WHERE fs.farm_id=%s
                """, (farm_id,)).fetchone()["species_name"]

            with (patch("client._api", side_effect=transport), patch("client.fetch_regions", return_value=(["통영시"], False))):
                app = AppTest.from_file(APP, default_timeout=20).run()
                app.button(key="start_button").click().run()
                app.selectbox(key="farm_region").select(app.selectbox(key="farm_region").options[0]).run()
                app.selectbox(key="farm_district").select(app.selectbox(key="farm_district").options[0]).run()
                app.selectbox(key="farm_species").select("전복").run()
                app.segmented_control(key="farm_abalone_kind").set_value("해상").run()
                app.session_state["farm_insurance"] = "미가입"
                next(b for b in app.button if b.label == "등록하기").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["page"], "risk")
                farm_id = app.session_state["remote_farm_id"]
                customer_id = app.session_state["customer"]["customer_id"]
                self.assertEqual(stored_species(farm_id), "전복(해상)")
                app.button(key="header_login").click().run()
                next(b for b in app.button if b.label == "회원가입").click().run()
                app.text_input[0].set_value("전복 품종 테스트")
                app.date_input[0].set_value(date(1980, 1, 1))
                app.text_input[1].set_value("01012345678")
                app.text_input(key="signup_password").set_value("test-password")
                next(b for b in app.button if b.label == "가입완료").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["customer"]["customer_id"], customer_id)
                app.button(key="header_logout").click().run()
                app.button(key="header_login").click().run()
                app.text_input[0].set_value("01012345678")
                app.text_input(key="login_password").set_value("test-password")
                next(b for b in app.button if b.label == "로그인").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["remote_farm_id"], farm_id)
                self.assertEqual(app.session_state["farm"]["abalone_kind"], "해상")
                next(b for b in app.button if b.label == "☰").click().run()
                app.button(key="nav_register").click().run()
                self.assertEqual(app.segmented_control(key="farm_abalone_kind").value, "해상")
                app.segmented_control(key="farm_abalone_kind").set_value("육상").run()
                next(b for b in app.button if b.label == "등록하기").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(stored_species(farm_id), "전복(육상)")


if __name__ == "__main__":
    unittest.main()
