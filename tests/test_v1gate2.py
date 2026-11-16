"""After the /v1 lock (Oliver via Gordon, legal 14.11.2026): the Scan Studio uploads only in Full Orbit (quiet note,
button dimmed, nothing sent), the statistics switch is dimmed outside Full Orbit with "(Full Orbit only)" and keeps the
stored choice, legal's privacy sentence verbatim, the 0.9.9 patch note.

    python -m unittest tests.test_v1gate2
"""
import pathlib
import unittest
from unittest import mock

from net import relay

ROOT = pathlib.Path(__file__).resolve().parents[1]
EN = ("Only in Full Orbit, which you turn on yourself: the exchange with friends (end-to-end encrypted), anonymous usage "
      "numbers if you also turn them on there (once a week, without any ID), and uploads from the Scan Studio.")
DE = ("Nur im „Ganzen Orbit“, den du selbst einschaltest: der Austausch mit Freunden (Ende-zu-Ende verschlüsselt), "
      "anonyme Nutzungszahlen, wenn du sie dort zusätzlich einschaltest (einmal pro Woche, ohne jede Kennung), und "
      "Uploads aus dem Scan-Studio.")


def settings(full):
    s = {"orbit": "near", "studio_consent": True}
    relay.state(s)["on"] = full
    return s


class Studio(unittest.TestCase):
    def backend(self, full):
        from ui import qstudio
        b = mock.Mock()
        b.ctrl.settings = settings(full)
        b.uploading = False
        b.full = lambda: qstudio.StudioBackend.full(b)
        return qstudio, b

    def test_nothing_goes_out_outside_full_orbit(self):
        qstudio, b = self.backend(False)
        with mock.patch("threading.Thread") as thread:
            qstudio.StudioBackend.upload_all(b)
            qstudio.StudioBackend.refresh_mine(b)
            qstudio.StudioBackend.uploadBox(b)
        thread.assert_not_called()
        b._local.assert_not_called()

    def test_full_orbit_uploads_as_before(self):
        qstudio, b = self.backend(True)
        self.assertTrue(b.full())
        b._local.return_value = []
        qstudio.StudioBackend.upload_all(b)
        b._local.assert_called()

    def test_note_and_dimmed_button(self):
        src = (ROOT / "ui" / "qstudio.py").read_text("utf-8")
        from ui import qstudio
        self.assertEqual(qstudio.UPLOAD_FULL_ONLY, "Uploading only works in Full Orbit")
        self.assertIn("enabled=bool(n) and bool(s.get(\"studio_consent\")) and full)", src)
        self.assertIn('ui.button(tr("Upload again"), self.upload_all, enabled=full)', src)


class Texts(unittest.TestCase):
    def setUp(self):
        from locales import de
        self.de = de

    def lookup(self, en):
        for name in dir(self.de):
            d = getattr(self.de, name)
            if isinstance(d, dict) and en in d:
                return d[en]
        return None

    def test_statistics_switch(self):
        src = (ROOT / "ui" / "qsetpages.py").read_text("utf-8")
        self.assertIn('+ ("" if full else " " + tr("(Full Orbit only)")), s.get("stats_share") is True', src)
        part = src[src.index('tr("Send anonymous numbers'):]
        self.assertIn("enabled=full)", part[:part.index("])")])
        self.assertEqual(self.lookup("(Full Orbit only)"), "(nur im Ganzen Orbit)")
        self.assertEqual(self.lookup("Uploading only works in Full Orbit"), "Hochladen geht nur im Ganzen Orbit")

    def test_team_messages_switch_stays_usable(self):
        """News come with the updates in every level; only the questions need the mailbox (lead 14.11.)."""
        src = (ROOT / "ui" / "qsetpages.py").read_text("utf-8")
        part = src[src.index('tr("Messages from the Bent°Corner team'):]
        part = part[:part.index("\n        ]")] if "\n        ]" in part else part[:600]
        outside = "Messages from the Bent°Corner team (news; questions about your contributions only in Full Orbit)"
        self.assertIn('if full else\n                 tr("' + outside + '")', part)
        self.assertNotIn("enabled=full", part[:part.index('signature.")') + 30])
        self.assertEqual(self.lookup(outside),
                         "Nachrichten vom Bent°Corner-Team (Neuigkeiten; Rückfragen zu deinen Beiträgen nur im Ganzen Orbit)")
        self.assertEqual(self.lookup("Messages from the Bent°Corner team (news, questions about your contributions)"),
                         "Nachrichten vom Bent°Corner-Team (Neuigkeiten, Rückfragen zu deinen Beiträgen)")

    def test_scan_data_send_is_only_a_local_zip(self):
        """„Senden …“ under scan data saves a ZIP on this PC – no network, nothing to lock (lead's question 14.11.)."""
        src = (ROOT / "app.py").read_text("utf-8")
        body = src[src.index("    def scandata_zip(self):"):src.index("    def scandata_clear(self):")]
        self.assertIn("scandata.make_zip(path)", body)
        for net in ("relay", "vault", "netpolite", "requests", "/v1"):
            self.assertNotIn(net, body)

    def test_privacy_sentence_verbatim(self):
        app = (ROOT / "app.py").read_text("utf-8").replace('"\n                    "', "")
        self.assertIn(EN, app)
        self.assertNotIn("Only if you turn them on", app)
        found = [v for name in dir(self.de) for k, v in (getattr(self.de, name).items()
                 if isinstance(getattr(self.de, name), dict) else []) if EN in str(k)]
        self.assertEqual(len(found), 1)
        self.assertIn(DE, found[0])
        self.assertNotIn("Nur wenn du es einschaltest", found[0])

    def test_patch_note(self):
        import version
        self.assertEqual(version.HIGHLIGHTS["0.9.9"][-1], "Scan Studio uploads are now only available in Full Orbit.")
        self.assertEqual(len(version.HIGHLIGHTS["0.9.9"]), 5)   # „Was ist neu?“ shows at most 5
        self.assertEqual(self.lookup("Scan Studio uploads are now only available in Full Orbit."),
                         "Uploads aus dem Scan-Studio gibt es nur noch im Ganzen Orbit.")
        # (until the 0.9.9 ship this also checked that VERSION was a work build of 0.9.9 – after the ship the work
        # builds count towards 0.9.10, so that line is gone)


if __name__ == "__main__":
    unittest.main()
