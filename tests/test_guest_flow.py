"""Guest navigation must work without an account or a running API."""
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class GuestFlowTest(unittest.TestCase):
    def test_registration_login_signup_and_guest_menu(self):
        with patch("client.fetch_regions", return_value=(["거제시"], False)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
            app.button(key="start_button").click().run()
            app.selectbox(key="farm_region").select("거제시").run()
            app.selectbox(key="farm_district").select(app.selectbox(key="farm_district").options[0])
            app.selectbox(key="farm_species").select("조피볼락 (우럭)")
            app.session_state["farm_method"] = "가두리"
            app.session_state["farm_insurance"] = "미가입"
            next(b for b in app.button if b.label == "등록하기").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["page"], "risk")
            self.assertNotIn("profile", app.session_state)
            farm = dict(app.session_state["farm"])

            next(b for b in app.button if b.label == "☰").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(m.value == "비회원으로 이용 중" for m in app.markdown))
            app.button(key="nav_insurance").click().run()
            self.assertEqual(app.session_state["page"], "insurance")
            self.assertFalse(app.exception)

            app.button(key="header_login").click().run()
            self.assertEqual(app.session_state["page"], "login")
            app.text_input[0].set_value("01012345678")
            app.text_input(key="login_password").set_value("example-password")
            next(b for b in app.button if b.label == "로그인").click().run()
            self.assertFalse(app.exception)
            self.assertNotIn("profile", app.session_state)
            self.assertEqual(app.text_input(key="login_password").value, "")

            next(b for b in app.button if b.label == "회원가입").click().run()
            self.assertEqual(app.session_state["page"], "signup")
            self.assertEqual(app.session_state["farm"], farm)
            next(b for b in app.button if b.label == "가입완료").click().run()
            self.assertTrue(app.error)
            app.text_input[0].set_value("홍길동")
            app.date_input[0].set_value(date(1980, 1, 1))
            app.text_input[1].set_value("01012345678")
            app.text_input(key="signup_password").set_value("example-password")
            next(b for b in app.button if b.label == "가입완료").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["page"], "risk")
            self.assertNotIn("signup_password", app.session_state)
            self.assertEqual(app.session_state["farm"], farm)

            app.button(key="header_login").click().run()
            next(b for b in app.button if b.label == "‹ 비회원으로 계속 이용").click().run()
            self.assertEqual(app.session_state["page"], "risk")
            next(b for b in app.button if b.label == "☰").click().run()
            app.button(key="nav_register").click().run()
            self.assertEqual(app.selectbox(key="farm_region").value, farm["region"])
            self.assertEqual(app.selectbox(key="farm_district").value, farm["district"])
            self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
