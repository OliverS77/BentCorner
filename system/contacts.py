"""Contact addresses of Bent°Corner – the only place where they are defined.

To change them (e.g. new address, server move): enter them here, then
    .venv\\Scripts\\python tools\\deploy_site.py   -> website (all links with data-mail="…") gets the new address
    build a new exe                              -> the app shows the new address (Studio, Settings)
The server's own mail settings (notification mailbox, SMTP) are not here: tools/server_contacts.py (private).
"""
MAILS = {
    "hello": "hello@bentcorner.app",       # general: contact page, legal notice, privacy policy, artists in the Studio
}
MAIL = MAILS["hello"]
SITE = "https://bentcorner.app"
CONTACT_PAGE = SITE + "/kontakt.html"
# Public source code (GPL-3.0, repository created by Oliver 03.11.2026). Settings → Legal links a release to its tag
# (source_url()); empty would hide the GPL notices (only for builds without a public source).
SOURCE_URL = "https://github.com/OliverS77/BentCorner"
# what SOURCE_URL must look like: a repository (GPL § 6: the way to the source), best with the release tag – never just
# a profile like https://github.com/<owner>/ (legal 03.11.2026); tests/test_gpl_notice.py and the export check it
SOURCE_PATTERN = r"^https://github\.com/[\w.-]+/[\w.-]+(/tree/[\w./-]+)?/?$"
# Our own server (updates, data packs, image mirror, mailbox). Since 0.9.2 the app asks SERVER first; SERVER_OLD is
# the former name of the same server – only a fallback if SERVER doesn't answer (net/netpolite.py: OLD_HOSTS).
# Installations up to 0.9.1 have SERVER_OLD built in: its update path stays open for a long time (docs/DOMAIN-PLAN.md).
SERVER = "https://bentcorner.app"
SERVER_OLD = "https://bentcorner.oliver-schunn.tech"
