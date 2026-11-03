<!-- LOGO: placeholder – Oliver chooses the version (mark / horizontal lockup / steps) before the first export. -->

# Bent°Corner

**Scan, collect and trade your trading cards – on your own PC.**

Bent°Corner is a free desktop app for trading card collectors. Hold a card up to your webcam and **SCAN°**
recognizes it in a moment. Your collection, binders, lists and decks stay on your computer; prices and
market data are fetched only if you want them.

Supported games: **Magic: The Gathering**, **Pokémon TCG**, **Yu-Gi-Oh!** and **Disney Lorcana**.

- **SCAN°** – card recognition via webcam, made for fast pack openings and streaming (stream view with live stats)
- **Library** – your collection with prices, price history and "Group by"
- **Decks** – deck building with rule warnings (deck size, copies, banlist, format legality)
- **Play** – shuffle, draw and check your opening-hand odds
- **Orbit** – you choose how far your data travels (see [Privacy](#privacy))

## Download

Get the latest version from **[bentcorner.app](https://bentcorner.app)**.
Windows 10/11 (64-bit). macOS and Linux are planned.

Updates are checked against a signed manifest; the update check can be turned off.
<!-- Add only once the Certum certificate is in use:
Releases are code-signed (certificate: *Open Source Developer, Oliver Schunn*). -->

## Uninstall

Bent°Corner has no installer. Its only change to Windows settings is the optional autostart entry
(registry value `BentCorner` under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`), which is removed when you
turn off "Keep running in the system tray" in the settings.

1. In the settings, turn off "Keep running in the system tray" (removes autostart), then close Bent°Corner.
2. Delete the program file `BentCorner.exe` (and `BentCorner.old.exe` next to it, if present).
3. Delete `%LOCALAPPDATA%\BentCorner` and `%APPDATA%\BentCorner` (small helper files; if your data folder is in
   a cloud folder, the program files "Bent°Corner Essentials" are here too).
4. Delete your data folder – this removes your collection. Default `Documents\BentCorner`; in portable mode it
   sits next to the program. It normally also contains the program files "Bent°Corner Essentials".
5. Optional: delete the `BentCorner backups` folders in the backup locations you chose.
<!-- performance: if the test PC shows a Qt cache in %LOCALAPPDATA%\Bent°Corner, add it to step 3. -->

## Privacy

Bent°Corner works without an account. In the **Orbit** setting you decide what leaves your computer:

- **Core** – everything stays with you.
- **Near Orbit** – you only fetch things (prices, market data). Nothing about you goes out.
- **Full Orbit** – you share: your lists, binders and tickets travel end-to-end encrypted to friends you choose.

Card data and recognition data are downloaded from the Bent°Corner server. Full privacy policy:
[bentcorner.app/datenschutz.html](https://bentcorner.app/datenschutz.html) (DE/EN).

## SCAN° and data packs

The source code of the app, **including the SCAN° recognition code**, is open under the GPL-3.0.

The **recognition data** (SCAN° models and the card fingerprint index) and the **card data packs** are
**not** part of this repository and **not** covered by the GPL. The app downloads them from the Bent°Corner
server. They may only be used with Bent°Corner and may not be redistributed. Card data from third parties
keeps its own license (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## How it was made

Bent°Corner is **vibe-coded**: concept, design, testing and every decision by Oliver Schunn; the code and
parts of the graphics were written with **Claude** (an AI by Anthropic). It works surprisingly well – please
read it with a wink.

## Build from source

Requirements: Windows 10/11, Python 3.12.

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` creates a `.venv`, installs the pinned `requirements.txt`, downloads the DINOv2 image model
(`Xenova/dinov2-small`, Apache-2.0) from Hugging Face at a fixed revision and checks its SHA-256, then builds
`dist\BentCorner.exe` with PyInstaller. GPU acceleration uses DirectML from Windows (version 1.15 or newer); it is
not bundled – without it Bent°Corner runs on the CPU. The build stops if a `DirectML*.dll` ends up in the program.

To run from source: `python app.py`. Tests: `python -m unittest discover -s tests -t .` – they run in a temporary
data folder and never touch your own collection.

What is **not** in this repository, and where the program gets it:

| Missing here | Comes from |
|---|---|
| DINOv2 image model | Hugging Face, fetched by `build.ps1` (see above) |
| SCAN° card fingerprint index, card databases, translated names | data packs the app downloads from the Bent°Corner server (Settings → Card data) |
| Card images | Magic: directly from Scryfall; Pokémon, Yu-Gi-Oh! and Disney Lorcana: via the Bent°Corner image mirror |
| Card-back filter (`cardback.npy`) | part of the Magic data pack (SCAN° data) – without it face-down cards are just not filtered out |

Without the data packs the app starts, but cards cannot be recognized by fingerprint.

### Data sources

Card data comes from [Scryfall](https://scryfall.com) and [MTGJSON](https://mtgjson.com) (Magic),
[TCGdex](https://tcgdex.dev) and [pokemontcg.io](https://pokemontcg.io) (Pokémon),
[YGOPRODeck](https://ygoprodeck.com) and [YGOJSON](https://github.com/iconmaster5326/YGOJSON) (Yu-Gi-Oh!) and
[LorcanaJSON](https://lorcanajson.org) (Disney Lorcana); prices from Cardmarket and TCGplayer (via
[TCGCSV](https://tcgcsv.com)). Licenses and required notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
The app keeps to each source's rules (`net/netpolite.py`: rate limits, caching).

## Forks and own builds

The code is yours to use under the GPL – our services and our brand are not.

- The Bent°Corner servers (data packs, SCAN° recognition data, image mirror, prices, mailbox/sync) may only be
  used by official Bent°Corner builds. Forks must change the server addresses (`system/contacts.py`) and run or
  find their own data sources – respecting the rules of each source.
- Forks must also use their own update signing key (`net/updater.py`) – official updates are signed with ours.
- Forks must use their own name and replace the brand assets listed in [brand/BRAND.md](brand/BRAND.md) (logos, icons,
  loading animation shape, splash images).

## Security

Found a security problem – for example in the encrypted exchange (Full Orbit), the update check or the data packs?
Please **don't open a public issue**. Report it privately via GitHub's "Report a vulnerability" (Security tab) or
by email to hello@bentcorner.app. We aim to reply within 14 days; please give us reasonable time to fix it before
you publish details.

Please test only with your own installation, data and IDs: don't access other people's data, don't overload or
attack the Bent°Corner servers, and don't test against other users. This is a free hobby project – there is no bug
bounty, but we're happy to credit you in the release notes if you like.

## Support

Bent°Corner is free – there is no paid version and nothing is locked behind a payment. If you'd like
to help with the server costs, you can buy Oliver a coffee: https://buymeacoffee.com/oliverschunn. Donations are
voluntary and come with no reward, perks or extra features.

## Contributing

Pull requests are not accepted for now. Bug reports and ideas are welcome as issues.
<!-- Default until Oliver decides. If PRs open later: decide on a CLA first (legal). -->

## License

- **Code:** [GNU General Public License v3.0](LICENSE), with additional terms under section 7:
  keep the attribution *"Based on Bent°Corner – https://bentcorner.app"* (naming the author is welcome, not
  required), mark modified versions, and use your own name for forks.
- **Brand assets** (logos, icons, loading animation shape, splash images): all rights reserved, see
  [brand/BRAND.md](brand/BRAND.md).
- **Other graphics and documentation made for this project:** [CC BY 4.0](LICENSE-ASSETS.md).
- **Third-party components and data:** see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Bent°Corner and SCAN° are names of this project and are not licensed for use by others.

Versions up to 0.9.6 were publicly released under the MIT License; from the first public release on, the GPL-3.0
with the additional terms applies.

## Fan project notice

Bent°Corner is an independent, free fan project. Donations are voluntary and pay for the server.
It is not affiliated with, endorsed, sponsored or approved by Wizards of the Coast, The Pokémon Company,
Nintendo, Creatures, GAME FREAK, Konami, 4K Media, Disney or Ravensburger. All trademarks, card names and card
images belong to their respective owners. This repository contains no card images and no card
databases (only a few card and set names as examples and test data).

Bent°Corner is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.
Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Pokémon and Pokémon character names are trademarks of Nintendo, Creatures Inc. and GAME FREAK inc.
Yu-Gi-Oh! is a trademark of Konami Digital Entertainment; card texts and images © 4K Media Inc. / Konami.
Uses trademarks and/or copyrights associated with Disney Lorcana TCG, used under Ravensburger's
[Community Code Policy](https://cdn.ravensburger.com/lorcana/community-code-en). We are expressly prohibited from
charging you to use or access this content. Bent°Corner is not published, endorsed, or specifically approved by
Disney or Ravensburger.

## Contact

hello@bentcorner.app · [bentcorner.app](https://bentcorner.app)
