"""CareCircle HTTP-layer tests — access control and validation via web.handle.

These call the same handler the local server and the Vercel adapter use,
so passing here means the deployed routes behave the same way.
"""

import json
import unittest
from datetime import datetime

from app import core, web

NOW = datetime(2026, 11, 15, 12, 0)


def call(method, path, payload=None, cookies=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    status, headers, raw = web.handle(method, path, "", body, cookies or {})
    return status, dict(headers), json.loads(raw or b"{}")


def login(role="caretaker", name="Ramesh Kumar", passcode=core.DEMO_PASSCODE):
    status, headers, _ = call("POST", "/api/login",
                              {"name": name, "role": role,
                               "passcode": passcode})
    assert status == 200, status
    cookie = headers["Set-Cookie"].split(";")[0].split("=", 1)[1]
    return {"cc_session": cookie}


class AccessControlTests(unittest.TestCase):
    def setUp(self):
        web.STORE = core.seed_store(NOW)

    def test_state_requires_login(self):
        status, _, payload = call("GET", "/api/state")
        self.assertEqual(status, 401)
        self.assertIn("error", payload)

    def test_wrong_passcode_rejected(self):
        status, _, _ = call("POST", "/api/login",
                            {"name": "X", "role": "elder",
                             "passcode": "wrong-pass"})
        self.assertEqual(status, 401)

    def test_unknown_role_rejected(self):
        status, _, _ = call("POST", "/api/login",
                            {"name": "X", "role": "admin",
                             "passcode": core.DEMO_PASSCODE})
        self.assertEqual(status, 400)

    def test_login_then_state_ok(self):
        cookies = login()
        status, _, payload = call("GET", "/api/state", cookies=cookies)
        self.assertEqual(status, 200)
        self.assertEqual(payload["elder"]["name"], "Kamla Devi")
        self.assertEqual(len(payload["medications"]), 4)

    def test_family_role_is_read_only(self):
        cookies = login(role="family", name="Priya Sharma")
        status, _, _ = call("POST", "/api/medications",
                            {"name": "New Med", "dose": "1 tablet",
                             "times": ["08:00"], "stock": 10},
                            cookies=cookies)
        self.assertEqual(status, 403)
        status, _, _ = call("POST", "/api/appointments",
                            {"doctor": "Dr X", "purpose": "Check",
                             "when": "2026-11-20", "time": "10:00"},
                            cookies=cookies)
        self.assertEqual(status, 403)

    def test_family_can_still_read_everything(self):
        cookies = login(role="family", name="Priya Sharma")
        status, _, payload = call("GET", "/api/state", cookies=cookies)
        self.assertEqual(status, 200)
        self.assertIn("summary", payload["assistant"])
        self.assertTrue(payload["feed"])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        web.STORE = core.seed_store(NOW)
        self.cookies = login()

    def test_add_medicine_appears_in_state_and_feed(self):
        status, _, _ = call("POST", "/api/medications",
                            {"name": "Omega 3", "dose": "1 capsule",
                             "times": ["13:00"], "stock": 20,
                             "category": "Supplement"},
                            cookies=self.cookies)
        self.assertEqual(status, 201)
        _, _, payload = call("GET", "/api/state", cookies=self.cookies)
        self.assertEqual(len(payload["medications"]), 5)
        self.assertTrue(any("Omega 3" in e["text"]
                            for e in payload["feed"]))

    def test_invalid_medicine_rejected(self):
        status, _, _ = call("POST", "/api/medications",
                            {"name": "Bad", "dose": "1 tablet",
                             "times": ["25:99"], "stock": 5},
                            cookies=self.cookies)
        self.assertEqual(status, 400)
        status, _, _ = call("POST", "/api/medications",
                            {"name": "", "dose": "1 tablet",
                             "times": ["08:00"], "stock": 5},
                            cookies=self.cookies)
        self.assertEqual(status, 400)

    def test_log_dose_decrements_stock_and_feeds(self):
        before = web.STORE.medications["med-metformin"].stock
        status, _, _ = call("POST", "/api/dose",
                            {"med_id": "med-metformin", "time": "09:00",
                             "status": "taken"}, cookies=self.cookies)
        self.assertEqual(status, 200)
        self.assertEqual(web.STORE.medications["med-metformin"].stock,
                         before - 1)
        _, _, payload = call("GET", "/api/state", cookies=self.cookies)
        self.assertTrue(any(e["kind"] == "dose_taken"
                            for e in payload["feed"]))

    def test_dose_for_unscheduled_time_rejected(self):
        status, _, _ = call("POST", "/api/dose",
                            {"med_id": "med-metformin", "time": "07:00",
                             "status": "taken"}, cookies=self.cookies)
        self.assertEqual(status, 400)

    def test_appointment_round_trip(self):
        status, _, payload = call("POST", "/api/appointments",
                                  {"doctor": "Dr. New", "purpose": "Eye test",
                                   "when": "2026-12-01", "time": "09:30"},
                                  cookies=self.cookies)
        self.assertEqual(status, 201)
        appt_id = payload["id"]
        status, _, _ = call("POST", f"/api/appointments/{appt_id}",
                            {"action": "delete"}, cookies=self.cookies)
        self.assertEqual(status, 200)
        _, _, payload = call("GET", "/api/state", cookies=self.cookies)
        self.assertFalse(any(a["id"] == appt_id
                             for a in payload["appointments"]))

    def test_health_is_public(self):
        status, _, payload = call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
