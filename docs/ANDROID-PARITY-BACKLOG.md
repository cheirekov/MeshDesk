# Android/Desktop parity backlog

Този backlog пази функциите, намерени при сравнението с актуалния официален
Meshtastic Android/Compose Desktop клиент. Той е inventory, а
`ROADMAP.md` определя реда за реализация.

Легенда:

- **P1** — висока практическа стойност за Linux клиента;
- **P2** — полезно след основите;
- **P3** — специализирано/голямо;
- **Hold** — изчаква стабилен upstream протокол или capability;
- **Skip** — Android-specific или извън фокуса на MeshDesk.

## Connection and desktop lifecycle

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| CON-01 | P1 | USB Serial discovery и transport | общ connection lifecycle | **completed** |
| CON-02 | P1 | TCP mDNS `_meshtastic._tcp` discovery | няма | **completed** |
| CON-03 | P1 | Recent devices и именувани connection profiles | profile identity | **completed** |
| CON-04 | P1 | Auto-reconnect с backoff и health state | CON-01/03 | **completed** |
| CON-05 | P1 | Native Linux notifications | notification preferences | queued |
| CON-06 | P2 | System tray/background mode | native desktop wrapper/PWA решение | queued |
| CON-07 | P2 | Keyboard shortcuts | стабилна navigation структура | queued |

## Channels

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| CH-01 | P1 | Пълен channel slot list, включително disabled | channel schema | **completed** |
| CH-02 | P1 | Add/edit/reorder/delete и PRIMARY validation | CH-01 | **started** |
| CH-03 | P1 | PSK generate/import със secret-safe handling | CH-02 | **completed** |
| CH-04 | P1 | Channel URL и QR import/export | CH-02/03 | queued |
| CH-05 | P2 | Remote channel administration | capability + PKI ACK | queued |
| CH-06 | P2 | Channel backup/restore diff | configuration snapshots | queued |

## Messaging

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| MSG-01 | P1 | Реален `reply_id` и quoted reply | packet model update | queued |
| MSG-02 | P1 | Emoji reactions | MSG-01 packet relationships | queued |
| MSG-03 | P1 | Пълни routing/delivery причини | unified delivery state | queued |
| MSG-04 | P1 | Store & Forward++ chain status | upstream SF++ support | queued |
| MSG-05 | P1 | Full-text conversation search | indexed encrypted history | queued |
| MSG-06 | P1 | History retention, dedup и export | history schema migration | queued |
| MSG-07 | P2 | Quick Chat templates | local preferences | queued |
| MSG-08 | P2 | Markdown rendering/toolbar | payload byte counter | queued |
| MSG-09 | P2 | `@node` mentions и navigation | node identity | queued |
| MSG-10 | P2 | Local delete/copy/share actions | history repository | queued |
| MSG-11 | P2 | Shared contacts/identity URL | PKI/contact schema | queued |
| MSG-12 | P1 | Queued → radio/enroute → ACK/NAK/timeout lifecycle | firmware queue status | **completed** |

## Nodes, trust and management

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| NODE-01 | P1 | Mute/unmute notifications | notification preferences | queued |
| NODE-02 | P1 | Remove node с безопасно потвърждение | NodeDB refresh | queued |
| NODE-03 | P2 | Локални operator notes и tags | local database | queued |
| NODE-04 | P1 | Online/unknown/infrastructure/MQTT filters | няма | queued |
| NODE-05 | P2 | Distance/channel/favorite sorting | position normalization | queued |
| NODE-06 | P2 | Nodes-per-hop histogram | time-window query | queued |
| NODE-07 | P1 | PKI lock/mismatch/trust indicators | public-key history | queued |
| NODE-08 | P2 | Device metadata, firmware и capabilities | metadata request/cache | **started** — session inventory за local и remote-admin target |
| NODE-09 | P2 | Hardware/product links | maintained upstream catalog | queued |
| NODE-10 | P1 | Explicit remote favorite/ignore с ACK/NAK/timeout | PKI admin | **completed** |

## Telemetry, diagnostics and topology

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| OBS-01 | P1 | Time-series telemetry storage | versioned local database | queued |
| OBS-02 | P1 | Device/environment/power/air charts | OBS-01 | queued |
| OBS-03 | P1 | CSV export и timeframe filters | OBS-01 | queued |
| OBS-04 | P1 | Neighbor Info request/ingestion | packet decoder/history | **started** |
| OBS-05 | P1 | Mesh topology graph | OBS-04 + node identity | queued |
| OBS-06 | P2 | Local Stats/congestion dashboard | OBS-01 | queued |
| OBS-07 | P2 | Position history | OBS-01 | queued |
| OBS-08 | P1 | Search/filter/export на packet и app logs | redaction pipeline | queued |
| OBS-09 | P2 | Discovery scan reports/history | DISC-01 | queued |
| OBS-10 | P1 | Android-compatible Traceroute/Neighbor cooldown с countdown | request lifecycle | **completed** |

## Map and spatial workflows

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| MAP-01 | P1 | Базова OpenStreetMap карта с node clustering | position model | queued |
| MAP-02 | P2 | Waypoint receive/send/edit/expire | waypoint packet model | queued |
| MAP-03 | P2 | Offline tile regions | MAP-01 storage policy | queued |
| MAP-04 | P3 | KML/KMZ/GeoJSON layers | MAP-01 | queued |
| MAP-05 | P3 | Geofence alerts | MAP-02 + background notifications | queued |
| MAP-06 | P3 | RF Site Planner | terrain data + propagation model | queued |
| MAP-07 | P2 | Traceroute/Neighbor overlay | MAP-01 + OBS-05 | queued |

## Configuration and security

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| CFG-01 | P1 | Contextual configuration help | guidance registry | **completed** |
| CFG-02 | P1 | Specialized forms, units и validation | schema metadata | **started** — общ descriptor metadata + curated firmware limits/units |
| CFG-03 | P1 | Firmware/capability-aware visibility | NODE-08 | **started** — section/action preflight без version guessing |
| CFG-04 | P2 | Region/preset compatibility advisor | capability + regulatory data | queued |
| CFG-05 | P2 | Encrypted security key backup/restore | explicit threat model | queued |
| CFG-06 | P2 | Protection level и identity-change warnings | firmware capability | queued |
| CFG-07 | P2 | Config bundle diff/signature/version | professional operation plan | queued |

Security key mutation остава умишлено извън общата dynamic форма. Публичните
identity данни са read-only, а encrypted backup/restore и identity rotation ще
се добавят след threat model, explicit confirmations и recovery workflow
(CFG-05/CFG-06).

## Professional/fleet track

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| PRO-01 | P1 | Fleet inventory и stable device identity | CON-03 + NODE-08 | queued |
| PRO-02 | P1 | Tags, saved selections и capability filters | PRO-01 | queued |
| PRO-03 | P1 | Dry-run operation planner и audit report | PRO-01 | queued |
| PRO-04 | P1 | Sequential LoRa command queue/budget | PRO-03 | queued |
| PRO-05 | P1 | Bulk favorite/ignore matrix | PRO-02/03/04 | queued |
| PRO-06 | P1 | Versioned single-device role profiles | CFG-02/03/07 | queued |
| PRO-07 | P1 | Canary/batched mass role configuration | PRO-04/06 | queued |
| PRO-08 | P2 | General mass config bundles | PRO-07 | queued |
| PRO-09 | P2 | Pause/resume/retry/stop policy | PRO-04 | queued |
| PRO-10 | P2 | Rollback coordinator | snapshots + reachability | queued |

## Discovery, firmware and integrations

| ID | Приоритет | Функция | Зависимости | Статус |
|---|---|---|---|---|
| DISC-01 | P3 | Local Mesh Discovery preset scanner | config snapshot/restore | queued |
| DISC-02 | P3 | Mesh Beacon invitations/join | upstream capability | queued |
| FW-01 | P2 | Installed firmware/update availability | NODE-08 | queued |
| FW-02 | P3 | USB/BLE/Wi-Fi OTA/DFU | signed manifest + recovery plan | queued |
| MQTT-01 | P2 | MQTT proxy through MeshDesk | broker/TLS lifecycle | queued |
| TAK-01 | P3 | Local TAK server/CoT integration | dedicated security design | queued |
| MOD-01 | P3 | Functional Canned Message UI | module protocol | queued |
| MOD-02 | P3 | Remote Hardware controls | capability + safety | queued |
| MOD-03 | P3 | Paxcounter dashboards | OBS-01 | queued |
| MOD-04 | Hold | Codec2 audio | upstream stability + audio stack | queued |

## Intentionally not in the MeshDesk core

| Функция | Решение |
|---|---|
| Android Auto | Skip — platform-specific |
| Wear OS | Skip — platform-specific |
| Android widgets | Skip — platform-specific |
| Android App Functions/system AI | Skip |
| Chirpy/AI summaries/translation | Skip for core; possible optional plugin later |
| NFC sharing | Skip for Linux core; QR/URL covers the main workflow |
| Shopping/device purchase links | Skip |
| Full embedded documentation browser | Later; contextual help and local docs have priority |

## Queue policy

Нова Android функция се добавя тук при откриване, дори когато няма да се
реализира веднага. Преминаване от `queued` към `in progress` става само след:

1. описан user outcome;
2. dependencies и protocol capability;
3. acceptance tests;
4. safety/privacy review;
5. избран milestone в `ROADMAP.md`.
