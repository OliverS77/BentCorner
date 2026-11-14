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
        if getattr(self, "poll_mode", lambda: False)():   # one question for vault and mailbox: ask now
            self.poll_now()
            return
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
        if relay.state(self.settings).get("leaving") and relay.enabled(self.settings):
            self.relay_toggle(False)   # leaving Full Orbit was cut off (app closed): finish it – withdraw, then off
            return
        if relay.enabled(self.settings):
            self._relay_t.start()
            self._lists_t.start()
            QtCore.QTimer.singleShot(4000, self._relay_tick)
        else:
            self._relay_t.stop()
            self._lists_t.stop()
        getattr(self, "poll_setup", lambda: None)()   # in poll mode the minute question takes over from _relay_t

    def relay_auto_lists(self):
        """Every 5 minutes: if shared lists have changed, only the changes go to the friends as small parcels
        (relay.send_delta). A complete re-share happens at most once a day (or when it expires soon,
        or with very many changes) – that also brings a shared Library up to date. It happens immediately
        via "Share with friends" on the Trade page (share_now)."""
        from net import relay
        if not relay.enabled(self.settings) or not relay.ok_friends(self.settings) or relay.state(self.settings).get("leaving"):
            return
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
        new = relay.fingerprint(self.relay_export())
        post = relay.posted(self.settings, games.current().key) or {}
        if relay.has_lib(new) != bool(post.get("lib")) or relay.has_lib(new) != relay.has_lib(old):
            # library switched on/off since the full post (or a post from before library deltas): never a delta that
            # adds or drops it – post everything anew, to exactly the friends of share_codes like every post
            self.relay_send_lists(quiet=True)
            return
        d = relay.delta(old, new)
        if not d or d == getattr(self, "_relay_last_delta", None):
            return
        s, game = self.settings, games.current().key
        codes = relay.share_codes(s)
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
        st = relay.state(self.settings)
        was = relay.enabled(self.settings)
        if was and not on and (st.get("posted") or {}):
            # leaving Full Orbit: take everything shared off the server FIRST (friends are notified) – the level drops
            # only when that is done, because outside Full Orbit the /v1 lock lets none of it out (lead 14.11.). The
            # mark "leaving" survives a closed app: the next start finishes it (relay_setup).
            if getattr(self, "_leaving_job", False):
                return
            self._leaving_job = True
            st["leaving"] = True
            self.settings_changed()
            for t in (getattr(self, "_relay_t", None), getattr(self, "_lists_t", None)):
                if t is not None:
                    t.stop()   # nothing new is shared while it is being taken back
            s = self.settings
            self._relay_quiet = False
            self._relay_bg("leave_full", lambda: relay.withdraw_all(s))
            return
        st.pop("leaving", None)
        st["on"] = bool(on)
        if on:
            relay.my_code(self.settings)   # create the key
        self.settings_changed()
        self.relay_setup()
        self._relay_ui()

    def _relay_ui(self):
        self.autobackup_badge()   # dot on the profile (open requests) + show the profile anew

    def _relay_bg(self, what, fn):
        """Network in the background, result in the main thread (bridge.relay_done)."""
        from net import relay

        def work():
            try:
                with relay.job():
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
        if getattr(self, "poll_mode", lambda: False)():   # the cheap question every 20 s instead of a whole mailbox fetch
            self.sync_poll_burst()
            return
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
        """Unblock – server first (lead 08.11., the web the same): /v1/block on:0, and only when the server took it the
        entry goes here. Offline or an error: nothing changes. relay_unblock_state = {code: "busy" | "offline" (no
        connection) | "failed" (the server refused) | "mailbox_off"} (library shows it in the profile's „Blocked“ box; on success the code leaves it and its row
        disappears). Mailbox off (Core Orbit): not here – the block may lie on the server, unblocking only here would
        leave it there and the person would silently not reach this ID back in Full Orbit (lead 08.11.)."""
        from net import relay
        s, code = self.settings, relay.norm(code)
        if not hasattr(self, "relay_unblock_state") or self.relay_unblock_state is None:
            self.relay_unblock_state = {}
        if self.relay_unblock_state.get(code) == "busy":
            return
        if not relay.enabled(s):
            if not relay.block_on_server(s, code):   # never on the server (a file import …): only here, at once
                self._unblock_local(code)
                return
            self.relay_unblock_state[code] = "mailbox_off"   # nothing changes – the box points to the Orbit settings
            self._relay_ui()
            return
        self.relay_unblock_state[code] = "busy"
        self._relay_ui()

        def work():   # -> "ok" | "offline" | "failed" (legal 08.11.: no connection told apart from a refusal)
            try:
                relay.server_block(s, code, False, strict=True)
                return "ok"
            except relay.RelayError as e:
                return "offline" if not e.status else "failed"
        self._relay_bg("unblock:" + code, work)

    def _unblock_local(self, code):
        from net import relay
        relay.unblock(self.settings, code)
        (getattr(self, "relay_unblock_state", None) or {}).pop(code, None)
        self.settings_changed()
        self._relay_ui()

    def _unblock_done(self, code, res, err):
        if err or res != "ok":   # the entry stays blocked here; the box says why
            self.relay_unblock_state[code] = res if res in ("offline", "failed") else "failed"
            self._relay_ui()
            return
        self._unblock_local(code)

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

    def relay_share_contents(self):
        """What goes to friends – ONE source for the parcel (relay_export, binders: qbinder.auto_share) and every view
        of it ("Shared with friends", the friends menu, later the profile preview; lead/legal 06.11.):
        {"lists": [(kind, list)] of the open game shared with friends, "library": bool, "binders": [(game, binder)]}"""
        from collection import trade
        from ui import qbinder
        lists = [(kind, x) for kind in ("wish", "have") for x in trade.lists(kind)
                 if not x.get("example") and trade.is_shared(x)]
        # an old "Yes" rests until answered (orbit.hold_sharing, legal 06.11.)
        return {"lists": lists, "library": self.settings.get("share_library") is True
                and not self.settings.get("share_library_paused"),
                "binders": qbinder.shared_binders(self)}

    def relay_export(self):
        """What gets shared: only trade and wish lists that are "shared with friends" (default: private)."""
        from collection import trade
        from system import userprofile
        prof = userprofile.ensure(self.settings)
        items = self.collection.items
        c = self.relay_share_contents()
        have_ids = [x["id"] for kind, x in c["lists"] if kind == "have"]
        have = trade.have_items(items, have_ids) if have_ids else []
        wl = [x["id"] for kind, x in c["lists"] if kind == "wish"]
        return trade.build_export(prof, items, "lists", trade.wishes(wl) if wl else None, None, have,
                                  library=c["library"])

    def relay_share_friend(self, code, on):
        """"Shared with friends": a friend gets everything I share – or nothing but name and card back. The audience is
        saved FIRST (no delta of the regular tick reaches them in between, ports 06.11.), then everything gets a new key
        for the friends switched on (relay_rekey: board_put replaces the content – the old key opens nothing new).
        Switched off, their app is asked to delete my shared content (board_gone, decided here – before the new posts
        rewrite who had what)."""
        from net import relay
        s = self.settings
        relay.set_share(s, code, on)
        self.settings_changed()
        if not relay.enabled(s):
            return
        if not on:
            had = relay.revoke_plan(s, code)
            if had:
                self._relay_bg("revoke", lambda: relay.revoke(s, code, had))
        self.relay_rekey()

    def share_audience_once(self):
        """On the update to per-friend sharing (06.11.): the friends of today keep what they get – see relay.py."""
        from net import relay
        if relay.migrate_audience(self.settings):
            self.settings_changed()

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
        s, game = self.settings, games.current().key
        if not (data.get("c") or data.get("w") or data.get("lib")):   # nothing shared any more: withdraw, not empty
            if relay.posted(s, game):
                self._relay_quiet = quiet
                self._relay_bg("withdraw", lambda: relay.withdraw(s, game))
            return True
        codes = relay.share_codes(s)
        self._relay_pending_fp = relay.fingerprint(data)
        self._relay_quiet = quiet   # automatic (hourly): no notice if it worked
        self._relay_bg("lists", lambda: relay.send_lists(s, data, game=game, audience=codes))
        return True

    def relay_share_library_off(self):
        """The library is no longer shared (the switch, or "Stop sharing" – lead/legal 06.11.: at once, in every game).
        The open game gets a new parcel without "lib". Another game's parcel can only be rebuilt while that game is
        open (automatic lists need its card database) – so if it may carry the library it is withdrawn now (friends
        delete their copy at once) and comes back without it the next time the game is open (relay_auto_lists: no
        post → share). Older posts don't know whether they had it ("lib" missing): withdrawn as well."""
        from net import relay
        s, cur = self.settings, games.current().key
        self.relay_send_lists(quiet=True)
        if not relay.enabled(s):
            return []
        others = [k.partition("/")[0] for k, v in (relay.state(s).get("posted") or {}).items()
                  if k.partition("/")[2] == relay.BOARD_LISTS and k.partition("/")[0] != cur
                  and (v or {}).get("lib") is not False]
        if others:
            self._relay_bg("withdraw_lib", lambda: [relay.withdraw(s, g) for g in others])
        return others

    @staticmethod
    def _relay_news(who, change):
        """Notice about something a friend shared (relay._change) – "" = nothing visible is new."""
        return {"lists": tr(f"New lists from {who}"),
                "library": tr(f"{who} is sharing their collection with you – see Trade")}.get(change, "")

    def _relay_tickets(self, events):
        """Trade tickets from the mailbox (net/relay.apply checked them): offers / counter-offers filed, a closing
        ticket waits to be booked ("closing"), a withdrawal marks the open offer – no dialog, in the ticket's game.
        Sets ev["filed"]; -> True if something changed"""
        from collection import offers
        from system import userprofile
        changed = False
        for ev in events:
            try:
                if ev["kind"] == "ticket":
                    ev["filed"] = offers.from_mailbox(ev["ticket"], userprofile.ensure(self.settings).get("id"))
                elif ev["kind"] == "ticket_gone":
                    ev["filed"] = offers.gone_from_mailbox(ev["x"], ev.get("pid") or "", ev.get("why") or "withdrawn")
                else:
                    continue
            except Exception:  # noqa: BLE001
                log.exception("Mailbox: trade ticket")
                ev["filed"] = None
            changed = changed or bool(ev.get("filed"))
        return changed

    # ---------- trade tickets through the mailbox (lead 06.11.: one click "Send to <friend>", never silently) ----------
    def relay_send_ticket(self, t, code):
        """Send a ticket to a mailbox friend in the background; the result lands in the offer (offers.set_mail) and
        the export page redraws. Never called just because a ticket is made or shown."""
        from net import relay
        s = self.settings
        x = t.get("x") or t["id"]

        def go():
            try:
                relay.send_ticket(s, code, t)
                return {"x": x, "g": t.get("g"), "ok": True, "status": 200, "t": time.time()}
            except relay.RelayError as e:
                return {"x": x, "g": t.get("g"), "ok": False, "status": e.status, "t": time.time()}
        self._relay_bg("ticket_send", go)

    def relay_send_ticket_gone(self, code, trade_id, version, why, game=None):
        from net import relay
        s = self.settings

        def go():
            try:
                relay.send_ticket_gone(s, code, trade_id, version, why)
                return {"x": trade_id, "g": game, "ok": True, "status": 200, "t": time.time()}
            except relay.RelayError as e:
                return {"x": trade_id, "g": game, "ok": False, "status": e.status, "t": time.time()}
        self._relay_bg("ticket_send", go)

    def _relay_done(self, what, res, err):
        from net import relay
        if what.startswith("unblock:"):
            return self._unblock_done(what.split(":", 1)[1], res, err)
        toast = getattr(getattr(self, "shell", None), "show_toast", None) or self.stream_toast
        if what == "leave_full":   # everything shared is taken back (or tried): now the level drops
            if err:
                toast(tr(f"Taking it back didn't work: {err}"))
            else:
                try:
                    self.relay_fp_file().unlink()
                except OSError:
                    pass
                toast(tr("You're not sharing anything right now – taken off the server; your friends' apps are asked to delete their copy."))
            self._leaving_job = False
            st = relay.state(self.settings)
            st.pop("leaving", None)
            st["on"] = False
            self.settings_changed()
            self.relay_setup()
            self._relay_ui()
            return
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
            if self._relay_tickets(names):   # trade tickets through the mailbox: filed under Trade offers
                self.trade_offers_changed(open_folder=False)
            for ev in names[:4]:
                who = ev.get("name") or relay.pretty(ev["code"])
                if ev["kind"] == "board_key" and str(ev["slot"]).startswith("binder-"):
                    toast(tr(f"{who} posted a binder for you – see Profile"))
                if ev["kind"] == "board_gone" and ev.get("had", True):   # nothing was visible on my side: quiet
                    what_ = tr("a binder") if str(ev.get("slot")).startswith("binder-") else tr("their lists")
                    toast(tr(f"{who} no longer shares {what_} in {games.nick_of(ev.get('game') or '')} with you – that's why it disappeared on your side."))
                if ev["kind"] == "ticket" and ev.get("filed"):
                    toast(tr(f"Trade offer from {who} received – Orbit → Trade offers") if ev["filed"] == "received"
                          else tr(f"{who} accepted – book it under Trade offers"))
                if ev["kind"] == "ticket_gone" and ev.get("filed"):
                    toast(tr(f"{who} declined.") if ev.get("why") == "declined" else tr(f"{who} withdrew the offer."))
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
        elif what == "ticket_send":
            from collection import offers
            if res:
                try:
                    offers.set_mail(res["x"], {k: res[k] for k in ("ok", "status", "t")}, res.get("g"))
                except Exception:  # noqa: BLE001
                    log.exception("Mailbox: ticket state")
            ip = getattr(self, "import_page", None)
            if ip is not None and hasattr(ip, "mail_done"):
                ip.mail_done(res)
            self.trade_offers_changed()
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
        elif what == "withdraw_lib":   # other games' parcels with the library (relay_share_library_off): quietly
            if err:
                log.info("Mailbox: withdrawing the library of other games: %s", err)
            self.settings_changed()
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
                    toast(tr("You're not sharing anything right now – taken off the server; your friends' apps are asked to delete their copy."))
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
