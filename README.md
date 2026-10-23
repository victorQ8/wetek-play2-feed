# WeTek Play 2 compatible Enigma2 feed

26 user plugins plus 2 automatic helper dependencies for the experimental
WeTek Play 2 S905/GXBB port, Python 3.13/AArch64. This is not an official OpenATV
release or a feed for other receivers. Requires `wetek-enigma2-api 20261023`.

Open **Menu → Plugins → green (Download Plugins)**. Extension Packages contains
most add-ons; System Plugins contains M3UIPTV. Installed packages appear under
red (Remove Plugins), and Manage shows both installed and available packages.
Restart the GUI when requested after installing a plugin with startup hooks.

Highlights: OpenWebif, M3UIPTV, EPGImport, AutoTimer, EPGRefresh, EPGSearch, IMDb,
SimpleRSS, PiconManager, Partnerbox, recording-library utilities, clock and
channel-history tools, WakeOnLan, Sudoku, Tetris and eSame. YouTube is already
bundled in the firmware and is not counted again here.

`catalog.json` lists all packages, licenses and pinned sources. The matching
`feed/py313-v1/catalog-v2.json` and Packages index let the compatible manager
accept catalog additions without another firmware flash. Metadata and the
index switch together; an interrupted or inconsistent refresh retains the
previous complete catalog. Payloads and the installed database persist on the
receiver's existing data filesystem. Core/kernel packages and foreign IPKs
are excluded from this plugin-only installer.

See `validation.json` for actual receiver checks. All 26 user-plugin entry
screens were checked on the receiver. OpenWebif's UI/API/assets, IMDb search,
RSS parsing and generated M3U/XMLTV/HTTP H.264 playback received additional
checks. This does not establish satellite reception, recording, every IPTV
provider, external partner receivers or every feature of every plugin.
HTTP transport-stream seeking remains unvalidated after a failed position
check; normal playback and pause passed. Transcoding, browser video capture
and unsupported codecs are not added by installing OpenWebif.

Complete upstream source archives, local patches and provenance are included.
Original notices/licenses are preserved inside each package. Several plugins
use CC BY-NC-SA 3.0 with an upstream alternative-license clause. This feed is
provided without charge for noncommercial use; consult each package's exact
license. GPL-2.0 text is copied from the pinned opkg source's COPYING file.
Excluded candidates and their reasons are recorded in `exclusions.json`.

The feed contains no firmware, provider subscriptions, credentials, or private
receiver configuration. Public metadata uses verified HTTPS and package
SHA-256 checks; the catalog/index is not independently signed.
