"""Friends online for the main window: mailbox timers and pace, share/fetch, requests, block/report, export, the
answers of the background jobs (relay.py does the protocol). APP-SPLIT phase C."""
import logging
import threading
import time

from PySide6 import QtCore, QtGui

import games
from collection import decks
from system import contacts
from system.i18n import tr
from ui import qdialogs

log = logging.getLogger("booster")   # the same logger as app.py


class RelayControl:
    """Mixin of MainWindow (app.py) – moved there unchanged (docs/APP-SPLIT.md, phase C). self is the MainWindow."""

    # ---------- Friends online (mailbox, relay.py) ----------
    RELAY_EVERY = 180   # s between two fetches (only when switched on)
    LISTS_EVERY = 300   # s: sync own lists – only changes (small parcels), complete at most once a day
    RELAY_IDLE_EVERY = 15 * 60   # SERVER-REGELN 6: nobody at the PC for 30 min (activity.idle) -> both every 15 min

    @property
    def activity(self):
        a = self.__dict__.get("_activity")
        if a is None:
            from system import activity
            a = self._activity = activity.Activity(self, on_wake=self._relay_wake)
        return a

    def _relay_pace(self):
        """Timers at the normal pace – or slow while nobody is at the PC (window untouched, app in the tray)."""
        slow = self.activity.idle()
        for t, every in ((self._relay_t, self.RELAY_EVERY), (self._lists_t, self.LISTS_EVERY)):
            want = (max(every, self.RELAY_IDLE_EVERY) if slow else every) * 1000
            if t.interval() != want:
                t.setInterval(want)

    def _relay_tick(self):
        self._relay_pace()
        self._relay_last = time.monotonic()
        self.relay_poll()

    def _relay_wake(self):
        """First input after a long pause: back to the normal pace, and fetch now if the last fetch is old."""
        from net import relay
        if getattr(self, "_relay_t", None) is None or not relay.enabled(self.settings):
            return
        self._relay_pace()
        if time.monotonic() - getattr(self, "_relay_last", 0.0) > self.RELAY_EVERY:
            self._relay_t.start()   # restart the round from now
            QtCore.QTimer.singleShot(1500, self._relay_tick)

    def relay_setup(self):
        if getattr(self, "_relay_t", None) is None:
            self._relay_t = QtCore.QTimer(self, interval=self.RELAY_EVERY * 1000, timeout=self._relay_tick)
            self._lists_t = QtCore.QTimer(self, interval=self.LISTS_EVERY * 1000, timeout=self.relay_auto_lists)
            self.bridge.relay_done.connect(self._relay_done)
        from net import relay
        if relay.enabled(self.settings):
            self._relay_t.start()
            self._lists_t.start()
            QtCore.QTimer.singleShot(4000, self._relay_tick)
        else:
            self._relay_t.stop()
            self._lists_t.stop()

    def relay_auto_lists(self):
        """Every 5 minutes: if shared lists have changed, only the changes go to the friends as small parcels
        (relay.send_delta). A complete re-share happens at most once a day (or when it expires soon,
        or with very many changes) – that also brings a shared Library up to date. It happens immediately
        via "Share with friends" on the Trade page (share_now)."""
        from net import relay
        if not relay.enabled(self.settings) or not relay.ok_friends(self.settings):
            return
        if self.settings.get("share_library") is None:   # friends are there: ask once (not in the background tick)
            QtCore.QTimer.singleShot(0, self.share_library_ask)
        try:
            n = self.relay_changes()
        except Exception:  # noqa: BLE001
            log.exception("Comparing lists")
            return
        try:   # shared binders (all games): only re-share if something changed
            from ui import qbinder
            qbinder.auto_share(self)
        except Exception:  # noqa: BLE001
            log.exception("Sharing binder")
        post = relay.posted(self.settings, games.current().key) or {}
        soon = (post.get("until") or 0) - time.time() < 24 * 3600
        day_old = time.time() - float(post.get("t") or 0) > 22 * 3600
        if not post or (post and soon) or ((n is None or n > 0) and day_old) or (n or 0) > relay.DELTA_MAX \
                or post.get("stale"):   # taken off the server after a block (relay.retire): post with a new key
            self.relay_send_lists(quiet=True)
        elif n:
            self.relay_send_delta()

    def relay_send_delta(self):
        """Send only the changes since the last complete state (absolute counts) – and only if something
        has happened again since the last parcel."""
        import json as _json
        from net import relay
        from system import userprofile
        try:
            old = _json.loads(self.relay_fp_file().read_text("utf-8"))
        except (OSError, ValueError):
            return
        d = relay.delta(old, relay.fingerprint(self.relay_export()))
        if not d or d == getattr(self, "_relay_last_delta", None):
            return
        post = relay.posted(self.settings, games.current().key) or {}
        aud = relay.state(self.settings).get("audience") or {}
        s, game = self.settings, games.current().key
        codes = relay.audience_codes(s, aud.get("mode") or "all", aud.get("codes") or ())
        pid = userprofile.ensure(s).get("id")
        self._relay_last_delta = d
        self._relay_bg("delta", lambda: relay.send_delta(s, game, post.get("t") or 0, d, pid, codes))

    SYNC_PAUSE = 300   # "Share with friends" / "Get from friends" rest for 5 minutes each afterwards

    def share_now(self):
        """Button "Share with friends": share the shared lists (and Library) completely now."""
        from net import relay
        if not relay.enabled(self.settings):
            self.relay_ask()
            if not relay.enabled(self.settings):
                return False
        if time.time() - float(self.settings.get("share_last") or 0) < self.SYNC_PAUSE:
            return False
        if not relay.ok_friends(self.settings):
            self.stream_toast(tr("No friends yet – add them by ID in your profile first."))
            return False
        self.settings["share_last"] = time.time()
        self.settings_changed()
        self.relay_send_lists(quiet=False)
        return True

    def fetch_now(self):
        """Button "Get from friends": empty the mailbox and re-fetch what all friends shared (open game)."""
        from net import relay
        if not relay.enabled(self.settings):
            self.relay_ask()
            if not relay.enabled(self.settings):
                return False
        if time.time() - float(self.settings.get("fetch_last") or 0) < self.SYNC_PAUSE:
            return False
        self.settings["fetch_last"] = time.time()
        self.settings_changed()
        self.relay_poll(manual=True)
        s, g = self.settings, games.current().key
        for code, f in relay.ok_friends(s).items():
            if f"{g}/{relay.BOARD_LISTS}" in (f.get("boards") or {}):
                self._relay_bg("board", lambda c=code: (relay.fetch_board(s, c, g), c)[1])
        self.stream_toast(tr("Checking on your friends …"))
        return True

    def relay_ask(self):
        """Consent: switch to Full Orbit = the exchange via the server (Bent°Corner Orbit; back under Settings →
        Friends & privacy)."""
        answer = qdialogs.ask(
            tr("Full Orbit – share with friends"),
            tr("This lets you add friends by their ID and share lists and binders with them.\n\nEverything is end-to-end encrypted: the server only sees a random ID and encrypted parcels – no names, no cards. Parcels are deleted once fetched, IP addresses are not stored.\n\nBack to Near Orbit any time under Settings → Friends & privacy.") + "\n\n" +
            tr("By turning it on you accept the terms of use: share nothing illegal, offensive or insulting – you can block and report friends."),
            [("privacy", tr("Read privacy policy"), ""), ("terms", tr("Terms of use"), ""), ("no", tr("Not now"), ""),
             ("yes", tr("Switch to Full Orbit"), "active")])
        if answer in ("privacy", "terms"):
            page = "datenschutz.html" if answer == "privacy" else "nutzung.html"
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(contacts.SITE + "/" + page))
            return self.relay_ask()
        if answer == "yes":
            self.settings["orbit_asked"] = True
            self.relay_toggle(True)

    def relay_toggle(self, on):
        from net import relay
        was = relay.enabled(self.settings)
        if was and not on and (relay.state(self.settings).get("posted") or {}):
            # exchange off: take everything shared off the server immediately (friends are notified)
            s = self.settings
            self._relay_quiet = False
            self._relay_bg("withdraw", lambda: relay.withdraw_all(s))
        relay.state(self.settings)["on"] = bool(on)
        if on:
            relay.my_code(self.settings)   # create the key
        self.settings_changed()
        self.relay_setup()
        self._relay_ui()

    def _relay_ui(self):
        self.autobackup_badge()   # dot on the profile (open requests) + show the profile anew

    def _relay_bg(self, what, fn):
        """Network in the background, result in the main thread (bridge.relay_done)."""
        def work():
            try:
                res, err = fn(), ""
            except Exception as e:  # noqa: BLE001
                res, err = None, str(e)
                if not isinstance(e, __import__("net.relay", fromlist=["relay"]).RelayError):
                    log.exception("Mailbox: %s", what)
            try:
                self.bridge.relay_done.emit(what, res, err)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def relay_poll(self, manual=False):
        from net import relay
        if not relay.enabled(self.settings) or getattr(self, "_relay_busy", False):
            return
        self._relay_busy = True
        s = self.settings
        self._relay_bg("poll_manual" if manual else "poll", lambda: relay.fetch(s))

    def relay_add(self, code):
        from net import relay
        s = self.settings
        self._relay_bg("add", lambda: relay.request_friend(s, code))

    RELAY_FAST, RELAY_FAST_FOR = 20, 300   # after a request/accept: check every 20 s for 5 minutes

    def relay_burst(self):
        """Just requested or accepted: fetch more often for a while so the answer arrives quickly (otherwise it
        only came with the next 3-minute round)."""
        self._relay_fast_until = time.time() + self.RELAY_FAST_FOR
        t = getattr(self, "_relay_fast_t", None)
        if t is None:
            def tick():
                if time.time() > getattr(self, "_relay_fast_until", 0):
                    self._relay_fast_t.stop()
                    return
                self.relay_poll()
            t = self._relay_fast_t = QtCore.QTimer(self, interval=self.RELAY_FAST * 1000, timeout=tick)
        t.start()

    def relay_answer(self, code, accept):
        from net import relay
        s = self.settings
        self._relay_bg("answer", lambda: (relay.answer_friend(s, code, accept), accept)[1])

    def relay_fetch(self, code):
        """"Fetch again": what a friend shared for the open game."""
        from net import relay
        s, g = self.settings, games.current().key
        self._relay_bg("board", lambda: (relay.fetch_board(s, code, g), code)[1])

    def relay_hide_back(self, code, on):
        from net import relay
        relay.set_hide_back(self.settings, code, on)
        self.settings_changed()
        self.trade_changed()
        self._relay_ui()

    def relay_block(self, code):
        from net import relay
        f = relay.friends(self.settings).get(relay.norm(code)) or {}
        if not qdialogs.question(tr("Block"), tr(f"Block {f.get('name') or relay.pretty(code)}? You won't get anything from this ID any more – not even new requests – and their lists disappear. You can undo this in your profile.")):
            return
        relay.block(self.settings, code)
        self._relay_blocked(code)

    def _relay_blocked(self, code):
        """After a block: refresh the views, tell the server (per-recipient block) and give everything I share a new
        key – the blocked ID still holds the old one."""
        from net import relay
        self.settings_changed()
        tp = getattr(self, "trade_page", None)
        if tp is not None and hasattr(tp, "reload_friends"):
            tp.reload_friends()
        self.trade_changed()
        self._relay_ui()
        s = self.settings
        if relay.enabled(s):
            self._relay_bg("block", lambda: relay.server_block(s, code, True))
        self.relay_rekey()

    def relay_rekey(self):
        """Blocked or removed a friend: post my lists and shared binders again with a NEW random key, so only the
        remaining friends get it (board_put sends board_key only to accepted friends). The old content on the server
        is replaced – the old key no longer opens anything. In the background like every mailbox job."""
        from net import relay
        s = self.settings
        if not relay.enabled(s) or not relay.state(s).get("posted"):
            return
        if not relay.ok_friends(s):   # nobody left to share with: take everything off the server
            self._relay_quiet = True
            self._relay_bg("withdraw", lambda: relay.withdraw_all(s))
            return
        cur, others = relay.rekey_plan(s, games.current().key)
        if cur:
            self.relay_send_lists(quiet=True)
        try:
            from ui import qbinder
            qbinder.auto_share(self, force=True)
        except Exception:  # noqa: BLE001
            log.exception("Sharing binders anew")
        if others:
            self._relay_bg("rekey", lambda: relay.retire(s, others))

    def relay_unblock(self, code):
        from net import relay
        relay.unblock(self.settings, code)
        self.settings_changed()
        self._relay_ui()
        s = self.settings
        if relay.enabled(s):
            self._relay_bg("block", lambda: relay.server_block(s, code, False))

    def relay_report(self, code):
        """Report: choose a reason, optional note – what you see of them is sent along (name, card back, title)."""
        from net import relay
        f = relay.friends(self.settings).get(relay.norm(code)) or {}
        st = {"reason": "illegal", "note": "", "block": True}

        def build(ui, d):
            return ui.col([
                ui.label(tr(f"Report {f.get('name') or relay.pretty(code)}"), big=True),
                ui.note(tr("Bent°Corner can't read along – so you send what you see: name, card back and the titles of their shared lists and binders. Oliver reviews every report and blocks the ID if needed.")),
                ui.form([(tr("Reason"), ui.combo([(k, tr(t)) for k, t in relay.REPORT_REASONS], st["reason"],
                                                lambda v: st.update(reason=v))),
                         (tr("Note"), ui.edit("", lambda t: st.update(note=t), live=lambda t: st.update(note=t),
                                               placeholder=tr("optional – what exactly?")))]),
                ui.check(tr("Block right away"), True, lambda v: st.update(block=bool(v))),
                ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                        ui.button(tr("Report"), lambda: d.close("send"), active=True)]),
            ], spacing=10)
        if qdialogs.show(tr("Report"), build) != "send":
            return
        s, content = self.settings, relay.report_content(self.settings, code)
        reason, note = st["reason"], st["note"]
        self._relay_bg("report", lambda: relay.report(s, code, reason, note, content))
        if st["block"]:
            relay.block(self.settings, code)
            self._relay_blocked(code)

    def relay_remove(self, code):
        from net import relay
        was_ok = (relay.friends(self.settings).get(relay.norm(code)) or {}).get("status") == "ok"
        relay.remove_friend(self.settings, code)
        self.settings_changed()
        self._relay_ui()
        if was_ok:   # they had my keys: share anew without them
            self.relay_rekey()

    def _deck_name_counts(self):
        """{card name: count in decks} – for automatic trade lists ("exclude from decks")."""
        from cards import carddb
        out = {}
        try:
            dl = decks.load()
            rows = carddb.cards_by_ids({c["sid"] for d in dl for c in d.get("cards") or []}) if carddb.exists() else {}
            for d in dl:
                for c in d.get("cards") or []:
                    r = rows.get(c["sid"])
                    if r and c.get("board", "main") == "main":
                        out[r["name"]] = max(out.get(r["name"], 0), int(c.get("count", 1)))
        except Exception:  # noqa: BLE001
            log.exception("Counting deck cards")
        return out

    def relay_export(self):
        """What gets shared: only trade and wish lists that are "shared with friends" (default: private)."""
        from collection import trade
        from system import userprofile
        prof = userprofile.ensure(self.settings)
        items = self.collection.items
        have_ids = [x["id"] for x in trade.lists("have") if not x.get("example") and trade.is_shared(x)]
        have = trade.have_items(items, have_ids) if have_ids else []
        wl = [x["id"] for x in trade.lists("wish") if not x.get("example") and trade.is_shared(x)]
        return trade.build_export(prof, items, "lists", trade.wishes(wl) if wl else None, None, have,
                                  library=self.settings.get("share_library") is True)

    def share_library_ask(self):
        """Ask once as soon as there are friends: make the Library visible to friends? (can be changed later under
        Settings → Friends & privacy). In the program window, without waiting."""
        if self.settings.get("share_library") is not None or getattr(self, "_share_lib_asked", False):
            return
        self._share_lib_asked = True

        def done(key):
            if key in ("yes", "no"):
                self.settings["share_library"] = key == "yes"
                self.settings_changed()
                if key == "yes":
                    self.relay_send_lists(quiet=True)
        qdialogs.ask(tr("Share your library with friends?"),
                     tr("Your friends will then see your whole collection of this game – encrypted, visible only to them. Lists are shared one by one (private / shared with friends).") + "\n\n" +
                     tr("You can change this later under Settings → Friends & privacy."),
                     [("no", tr("No, keep private"), ""), ("yes", tr("Yes, share with friends"), "active")],
                     wait=False, on_close=done)

    def relay_fp_file(self):
        from scanner import common
        return common.MINE / "posted-lists.json"

    def relay_changes(self):
        """Entries changed since the last share (added, removed, different count) – None if never shared."""
        import json as _json
        from net import relay
        try:
            old = _json.loads(self.relay_fp_file().read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return relay.changes(old, relay.fingerprint(self.relay_export()))

    def relay_send_lists(self, data=None, quiet=False):
        """Share lists (6 months, encrypted) and send the key to the chosen friends – on export
        and with "Share again". data: trade file (otherwise preset like "For friends")."""
        from net import relay
        if not relay.enabled(self.settings) or not relay.ok_friends(self.settings):
            return False
        data = data or self.relay_export()
        aud = relay.state(self.settings).get("audience") or {}
        s, game = self.settings, games.current().key
        if not (data.get("c") or data.get("w") or data.get("lib")):   # nothing shared any more: withdraw, not empty
            if relay.posted(s, game):
                self._relay_quiet = quiet
                self._relay_bg("withdraw", lambda: relay.withdraw(s, game))
            return True
        codes = relay.audience_codes(s, aud.get("mode") or "all", aud.get("codes") or ())
        self._relay_pending_fp = relay.fingerprint(data)
        self._relay_quiet = quiet   # automatic (hourly): no notice if it worked
        self._relay_bg("lists", lambda: relay.send_lists(s, data, game=game, audience=codes))
        return True

    @staticmethod
    def _relay_news(who, change):
        """Notice about something a friend shared (relay._change) – "" = nothing visible is new."""
        return {"lists": tr(f"New lists from {who}"),
                "library": tr(f"{who} is sharing their collection with you – see Trade")}.get(change, "")

    def _relay_done(self, what, res, err):
        from net import relay
        toast = getattr(getattr(self, "shell", None), "show_toast", None) or self.stream_toast
        if what.startswith("poll"):
            self._relay_busy = False
            if err:
                if what == "poll_manual":
                    toast(tr(f"Mailbox: {err}"))
                return
            envs, ids = res
            names = []
            for env in envs:
                try:
                    ev = relay.apply(self.settings, env)
                except Exception:  # noqa: BLE001
                    log.exception("Mailbox: parcel")
                    ev = None
                if ev:
                    names.append(ev)
            self.settings_changed()
            s = self.settings
            if ids:
                self._relay_bg("ack", lambda: relay.ack(s, ids))
            if any(ev["kind"] == "team" for ev in names):
                self.team_inbox_changed(toast=True)
            for ev in names[:4]:
                who = ev.get("name") or relay.pretty(ev["code"])
                if ev["kind"] == "board_key" and str(ev["slot"]).startswith("binder-"):
                    toast(tr(f"{who} posted a binder for you – see Profile"))
                if ev["kind"] == "board_gone" and ev.get("had", True):   # nothing was visible on my side: quiet
                    what_ = tr("a binder") if str(ev.get("slot")).startswith("binder-") else tr("their lists")
                    toast(tr(f"{who} no longer shares {what_} in {games.nick_of(ev.get('game') or '')} with you – that's why it disappeared on your side."))
                text = {"friend": tr(f"Friend request from {who} – see Profile"),
                        "friend_ok": tr(f"{who} accepted your request"),
                        "friend_no": tr(f"{who} declined"),
                        "list": self._relay_news(who, ev.get("change"))}.get(ev["kind"])
                if text:
                    toast(text)
            if any(ev["kind"] == "friend_ok" for ev in names):
                self.relay_send_lists()   # new friends get my lists right away
            for ev in names:   # a friend shared something: fetch it right away (in the background)
                if ev["kind"] == "board_key" and not str(ev["slot"]).startswith("binder-"):   # binders: when needed
                    s2, c, g, sl = self.settings, ev["code"], ev["game"], ev["slot"]
                    self._relay_bg("board", lambda s2=s2, c=c, g=g, sl=sl: (relay.fetch_board(s2, c, g, sl), c)[1])
                elif ev["kind"] == "list_delta" and ev.get("refetch"):   # complete state still missing: fetch it first
                    s2, c, g = self.settings, ev["code"], ev["game"]
                    self._relay_bg("board", lambda s2=s2, c=c, g=g: (relay.fetch_board(s2, c, g), c)[1])
            if any(ev["kind"] in ("list", "list_delta", "board_gone") for ev in names):
                tp = getattr(self, "trade_page", None)
                if tp is not None and hasattr(tp, "fill_friends"):
                    try:
                        tp.fill_friends()
                    except Exception:  # noqa: BLE001
                        log.exception("Reloading friends")
                self.trade_changed()
            if what == "poll_manual" and not names:
                toast(tr("Mailbox: nothing new"))
        elif what == "report":
            toast(tr(f"Report not sent: {err}") if err else tr("Thanks – the report has arrived."))
        elif what == "add":
            toast(tr(f"Request not sent: {err}") if err else tr("Request sent – once your friend accepts, you'll exchange lists."))
            self.settings_changed()
            self._relay_ui()   # appears at the top under "Requests" as "waiting for reply"
            if not err:
                self.relay_burst()
        elif what == "answer":
            if err:
                toast(tr(f"Answer not sent: {err}"))
            else:
                self.settings_changed()
                self._relay_ui()
                if res:
                    self.relay_send_lists()
                    self.relay_burst()   # the new friend's name and lists arrive shortly
        elif what == "lists":
            if err:
                toast(tr(f"Lists not posted: {err}"))
            else:
                n, errors = res
                fp = getattr(self, "_relay_pending_fp", None)
                if fp is not None:
                    try:
                        import json as _json
                        self.relay_fp_file().write_text(_json.dumps(fp), "utf-8")
                    except OSError:
                        pass
                self.settings_changed()
                if not getattr(self, "_relay_quiet", False) or errors:
                    toast(tr(f"Lists shared – with {n} friends") + (" · " + tr(f"{len(errors)} failed")
                                                                              if errors else ""))
        elif what == "withdraw":
            if err:
                toast(tr(f"Taking it back didn't work: {err}"))
            else:
                try:
                    self.relay_fp_file().unlink()
                except OSError:
                    pass
                self.settings_changed()
                if not getattr(self, "_relay_quiet", False):
                    toast(tr("You're not sharing anything right now – deleted from the server, your friends no longer see it."))
        elif what == "delta":
            if err or (res and res[1]):
                log.info("Changes to friends: %s", err or res[1])
        elif what == "binder_put":
            toast(tr(f"Binder not posted: {err}") if err else tr(f"Binder shared – with {res[0]} friends"))
            self.settings_changed()
        elif what in ("block", "rekey"):   # server block / retiring other games' lists: quiet (logged in relay)
            self.settings_changed()
        elif what in ("binder_put_quiet", "binder_gone"):   # tick or set to private: quiet, just remember
            if err:
                log.info("Binder (%s): %s", what, err)
            self.settings_changed()
        elif what == "binder_get":
            if err:
                toast(tr(f"Binder not loaded: {err}"))
            else:
                payload, who, *rest = res
                pb = getattr(getattr(self, "shell", None), "backends", {}).get("profile")
                if pb is not None:
                    back = self.stream.page if self.stream.page != "profile" else ""
                    pb.binder.open_friend(payload, who, rest[0] if rest else None)
                    if not pb.binder.show_in(self.stream.page):   # from the trade: shown right there
                        pb.binder.back_to = back
                        self.stream.show_page("profile", back=True)   # show it large (binder view in the profile)
        elif what == "board":
            if err:
                log.info("Fetching shared items: %s", err)
            else:
                self.settings_changed()
                f = relay.friends(self.settings).get(res) or {}
                news = self._relay_news(f.get("name") or relay.pretty(res), f.pop("last_change", None))
                if news:   # only report what's really new (empty list shared/private, same state: quiet)
                    toast(news)
                tp = getattr(self, "trade_page", None)
                if tp is not None and hasattr(tp, "fill_friends"):
                    try:
                        tp.fill_friends()
                    except Exception:  # noqa: BLE001
                        log.exception("Reloading friends")
                self.trade_changed()
        self._relay_ui()
