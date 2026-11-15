"""CareCircle core tests — security, schedule maths, reminders, assistant."""

import unittest
from datetime import datetime, timedelta

from app import core

NOW = datetime(2026, 11, 15, 12, 0)  # a Sunday at noon, fixed for determinism


class PasscodeTests(unittest.TestCase):
    def test_correct_passcode_verifies(self):
        salt, digest = core.hash_passcode("kamla123")
        self.assertTrue(core.verify_passcode("kamla123", salt, digest))

    def test_wrong_passcode_rejected(self):
        salt, digest = core.hash_passcode("kamla123")
        self.assertFalse(core.verify_passcode("kamla124", salt, digest))
        self.assertFalse(core.verify_passcode("", salt, digest))

    def test_salts_are_unique_and_no_plaintext(self):
        salt1, digest1 = core.hash_passcode("kamla123")
        salt2, digest2 = core.hash_passcode("kamla123")
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(digest1, digest2)
        self.assertNotIn("kamla123", digest1)

    def test_demo_profile_stores_only_a_hash(self):
        store = core.seed_store(NOW)
        self.assertNotEqual(store.profile.passcode_hash, core.DEMO_PASSCODE)
        self.assertTrue(core.verify_passcode(
            core.DEMO_PASSCODE, store.profile.passcode_salt,
            store.profile.passcode_hash))


class AdherenceTests(unittest.TestCase):
    def setUp(self):
        self.store = core.seed_store(NOW)

    def test_seven_day_adherence_matches_hand_count(self):
        # Seed rule gives exactly one missed dose in the previous 6 days;
        # today's 4 morning doses are due and unlogged at noon -> missed.
        result = core.adherence(self.store, 7, NOW)
        self.assertEqual(result["taken"], 29)
        self.assertEqual(result["missed"], 5)
        self.assertEqual(result["total"], 34)
        self.assertEqual(result["pct"], 85.3)

    def test_future_doses_are_not_counted(self):
        early = datetime(2026, 11, 15, 7, 0)  # before any dose today
        store = core.seed_store(early)
        result = core.adherence(store, 1, early)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["pct"], 100.0)

    def test_logging_a_dose_updates_adherence(self):
        self.store.log_dose("med-amlodipine", "2026-11-15", "08:00",
                            "taken", by="Kamla Devi", now=NOW)
        result = core.adherence(self.store, 7, NOW)
        self.assertEqual(result["taken"], 30)
        self.assertEqual(result["missed"], 4)


class RefillTests(unittest.TestCase):
    def test_metformin_runs_out_in_three_days(self):
        store = core.seed_store(NOW)
        est = core.refill_estimate(store.medications["med-metformin"],
                                   NOW.date())
        self.assertEqual(est["days_left"], 3)  # 6 units, 2 per day
        self.assertEqual(est["runs_out"], "2026-11-18")
        self.assertTrue(est["low"])

    def test_well_stocked_medicine_is_not_low(self):
        store = core.seed_store(NOW)
        est = core.refill_estimate(store.medications["med-vitd"], NOW.date())
        self.assertEqual(est["days_left"], 30)
        self.assertFalse(est["low"])


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.store = core.seed_store(NOW)
        self.reminders = core.compute_reminders(self.store, NOW)

    def test_all_four_morning_doses_are_missed_at_noon(self):
        names = {m["name"] for m in self.reminders["missed"]}
        self.assertEqual(names, {"Amlodipine 5 mg", "Telmisartan 40 mg",
                                 "Metformin 500 mg", "Vitamin D3"})

    def test_no_upcoming_dose_at_noon(self):
        self.assertEqual(self.reminders["upcoming"], [])

    def test_upcoming_dose_before_breakfast(self):
        early = datetime(2026, 11, 15, 7, 30)
        store = core.seed_store(early)
        reminders = core.compute_reminders(store, early)
        names = {m["name"] for m in reminders["upcoming"]}
        self.assertIn("Amlodipine 5 mg", names)  # 08:00, 30 min away
        self.assertEqual(reminders["missed"], [])

    def test_only_metformin_needs_a_refill(self):
        names = {m["name"] for m in self.reminders["refills"]}
        self.assertEqual(names, {"Metformin 500 mg"})

    def test_outbox_goes_to_elder_and_caretaker(self):
        new = core.generate_outbox(self.store, NOW)
        # 4 missed doses x (elder + caretaker) + 1 refill x 2 = 10
        self.assertEqual(len(new), 10)
        recipients = {(m.to_role, m.to_name) for m in new}
        self.assertIn(("elder", "Kamla Devi"), recipients)
        self.assertIn(("caretaker", "Ramesh Kumar"), recipients)
        self.assertFalse(any(m.to_role == "family" for m in new))

    def test_outbox_generation_is_idempotent(self):
        core.generate_outbox(self.store, NOW)
        self.assertEqual(core.generate_outbox(self.store, NOW), [])
        self.assertEqual(len(self.store.outbox), 10)

    def test_taken_dose_gets_no_missed_reminder(self):
        self.store.log_dose("med-amlodipine", "2026-11-15", "08:00",
                            "taken", by="Kamla Devi", now=NOW)
        reminders = core.compute_reminders(self.store, NOW)
        self.assertNotIn("Amlodipine 5 mg",
                         {m["name"] for m in reminders["missed"]})


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.store = core.seed_store(NOW)
        self.flags = core.safety_checks(self.store)

    def test_duplicate_therapy_flagged(self):
        kinds = {f["kind"] for f in self.flags}
        self.assertIn("duplicate_therapy", kinds)  # two blood-pressure meds

    def test_time_clash_flagged(self):
        kinds = {f["kind"] for f in self.flags}
        self.assertIn("time_clash", kinds)  # 08:00 vs 08:15, 09:00 vs 09:30

    def test_exact_duplicate_name_flagged_high(self):
        self.store.medications["med-copy"] = core.Medication(
            "med-copy", "Amlodipine 5 mg", "1 tablet", ["20:00"], stock=10)
        flags = core.safety_checks(self.store)
        dup = [f for f in flags if f["kind"] == "duplicate_name"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0]["severity"], "high")

    def test_no_flags_for_a_clean_schedule(self):
        salt, digest = core.hash_passcode("x")
        store = core.Store(core.Profile("Test Elder", 70, salt, digest))
        store.medications["m1"] = core.Medication(
            "m1", "Med A", "1 tablet", ["08:00"], stock=50, category="A")
        store.medications["m2"] = core.Medication(
            "m2", "Med B", "1 tablet", ["12:00"], stock=50, category="B")
        self.assertEqual(core.safety_checks(store), [])

    def test_daily_summary_is_plain_language(self):
        text = core.daily_summary(self.store, NOW)
        self.assertIn("Kamla", text)
        self.assertIn("0 of 4 doses", text)  # nothing logged yet today
        self.assertIn("21:00", text)  # next dose: evening Metformin
        self.assertIn("85%", text)  # 7-day adherence rounded


if __name__ == "__main__":
    unittest.main()
