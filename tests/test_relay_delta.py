"""Friends' changes over the relay (list_delta, net/relay.apply_delta) land on their stored list. Since 0.9.2.48 a
NameError ("folder") broke every delta – the changes only arrived with the daily complete share.

    python -m unittest tests/test_relay_delta.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import trade
from net import relay


class RelayDelta(unittest.TestCase):
    def test_delta_applies_to_stored_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            friends = pathlib.Path(tmp)
            (friends / "f1.json").write_text(json.dumps({"id": "f1", "name": "A", "wants": [["Pot of Greed", 1]],
                                                          "cards": [["dabl", "EN001", "ja", 0, 1],
                                                                    ["lob", "001", "en", 1, 2]]}), "utf-8")
            with mock.patch.object(trade, "friends_folder", lambda game: friends), \
                    mock.patch.object(trade, "FRIENDS", friends), mock.patch.object(relay, "fill_names", lambda d: None):
                self.assertTrue(relay.apply_delta("yugioh", "f1", {"dabl|EN001|ja|0": 3, "lob|001|en|1": 0,
                                                                     "mp22|EN257|en|0": 1, "w:Pot of Greed": 0}))
                self.assertFalse(relay.apply_delta("yugioh", "nobody", {"x|1|en|0": 1}))   # no list: fetch it whole
                self.assertIs(trade.FRIENDS, friends)
            d = json.loads((friends / "f1.json").read_text("utf-8"))
        self.assertEqual(sorted(c[:5] for c in d["cards"]), [["dabl", "EN001", "ja", 0, 3], ["mp22", "EN257", "en", 0, 1]])
        self.assertEqual(d["wants"], [])


if __name__ == "__main__":
    unittest.main()
