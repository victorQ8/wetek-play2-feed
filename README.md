# WeTek Play 2 experimental Enigma2 plugin feed

Curated Python 3.13 plugins for the custom S905/GXBB runtime. This is not an
OpenATV release or a general OpenATV feed. Packages require wetek-enigma2-api
20261023. Do not add this feed to other receivers or firmware.

Browse `feed/py313-v1/Packages` for package descriptions. `provenance.json`
records exact upstream revisions; complete source exports are in `sources/`.
Each plugin carries its original license and authorship notices. AddStreamUrl
is GPLv3; AutoTimer, EPGSearch and EPGRefresh are CC BY-NC-SA 3.0 with the
upstream alternative license clause. This feed is distributed without charge
for noncommercial use; those three plugins must not be commercially distributed
outside their upstream license terms. Refer to each included LICENSE.txt.

Package installation and screen checks do not establish satellite reception,
IPTV-provider compatibility or successful recordings. See validation.json for
actual receiver test results. This feed contains no firmware, credentials or
receiver-specific settings.

## On the receiver

Open **Menu → Plugins → green (Download Plugins) → Extension Packages**.
The initial catalog contains AddStreamUrl, AutoTimer, EPGRefresh and EPGSearch.
Installed packages appear under the red Remove Plugins action. The integrated
installer retains plugins and the package database across reboot. Package and
menu checks passed over this public HTTPS feed after a software reboot; see
[validation.json](validation.json) for the exact scope.
