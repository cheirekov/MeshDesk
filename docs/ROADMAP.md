# MeshDesk implementation roadmap

Roadmap-ът разделя обикновения Linux клиент от бъдещия professional/fleet слой.
Редът е умишлен: първо надеждност и наблюдаемост, след това масови промени.
Пълният inventory от Android сравнението е в
[`ANDROID-PARITY-BACKLOG.md`](ANDROID-PARITY-BACKLOG.md).

## Приоритетна рамка

- **P0 / core reliability** — connection lifecycle, честни delivery evidence,
  gateway диагностика и безопасност на admin/config writes.
- **P1 / professional operations** — наблюдаемост, inventory, export и
  подготвена основа за fleet/mass operations.
- **P2 / workflow depth** — допълнителни анализи и специализирани operator
  инструменти след стабилна P0/P1 основа.
- **Nice to have** — географска карта на чутите възли и opt-in AI обяснение.
  Те остават записани, но не изместват диагностиката и fleet safety.

## M0 — Documentation and guidance

Статус: **в процес**

- [x] Отделна документационна структура.
- [x] Role Advisor за `CLIENT`, `CLIENT_BASE`, `CLIENT_MUTE`, `ROUTER` и
  `ROUTER_LATE`.
- [x] Contextual help за чувствителни configuration секции.
- [x] Field-level help за radio/module/channel настройки и Administration.
- [x] Human-readable semantics за sentinel, duration, enum, bitmask и position
  precision стойности, без измислени hardware ranges.
- [ ] Централен searchable Help център в приложението.
- [ ] Firmware/capability обозначения към всяка настройка.

Критерий за завършеност: операторът може да разбере ефекта и риска на
настройката, преди да промени радиото.

## M1 — Connection reliability

- [x] USB Serial discovery и transport без системно инсталиране на Python пакети.
- [x] mDNS discovery за `_meshtastic._tcp` без системни пакети.
- [x] Именувани connection profiles с локално persistence и last-used metadata.
- [x] Verified device identity след handshake, mismatch защита и explicit rebind.
- [x] Контролирано profile opt-in auto-reconnect с backoff, identity guard и
  видимо състояние.
- [x] Health/liveness state, activity timestamps и ясна причина за прекъсване.

Критерий: TCP, BLE и Serial използват еднакъв lifecycle и не губят handshake
пакети или история.

## M1.5 — Remote NodeDB safety

- [x] Ясно разделяне на subject node и managed NodeDB.
- [x] Известно локално срещу неизвестно remote favorite/ignore състояние.
- [x] Отделни explicit add/remove и ignore/unignore remote действия.
- [x] Надеждно различаване на ACK, NAK и timeout.
- [x] Еднократно session refresh/retry при `ADMIN_BAD_SESSION_KEY`.
- [x] Stable local cache projection и защита от self-preference операции.
- [x] Audit резултат с `accepted, unverified` при непрочитаем remote state.
- [x] Capability/firmware preflight преди изпращане.

Този milestone беше поставен пред auto-reconnect и остава задължителна основа
за бъдещите mass operations, защото изисква еднозначно адресиране и честен
result model.

## M2 — Channel Manager

- [x] Списък на всички channel slots, включително disabled.
- [x] Добавяне, редактиране и изтриване.
- [ ] Explicit пренареждане на Secondary slots.
- [x] PRIMARY/SECONDARY правила и предварителна валидация.
- [x] Генериране/въвеждане на PSK без показване в логовете.
- [ ] Channel URL и QR import/export.
- [x] Backend-validated preview и encrypted backup преди запис.
- [x] Remote channel administration с explicit load, PKI ACK и post-read verify.

Критерий: каналите могат да се управляват безопасно, без CLI или Android.

## M3 — Professional messaging

- [ ] Реален `reply_id` и quoted reply.
- [ ] Emoji reactions.
- [ ] Пълни routing/delivery състояния и човешки обяснения.
- [x] Честен queued → radio/enroute → ACK/NAK/timeout lifecycle.
- [x] Разделяне на broadcast implicit ACK от destination ACK, включително
  backward-compatible rendering на старата история.
- [x] Evidence-first delivery timeline в Packet Inspector.
- [x] Видим firmware/application TX queue status без блокиране на HTTP/UI.
- [ ] Store & Forward++ статус.
- [ ] Full-text search, retention и export.
- [ ] Quick Chat и desktop notifications.

## M4 — Observability and topology

- [x] User Info, Neighbor Info, host и PAX telemetry заявки от Node Inspector.
- [x] Global traceroute и per-node Neighbor Info cooldown с backend enforcement.
- [ ] Time-series база за telemetry и position.
- [ ] Графики и CSV export.
- [x] Friendly Neighbor Info result с resolved node names, SNR и link metadata.
- [x] Canonical telemetry/position metric rendering с известен alias dedup,
  external-power marker и сгъваем original payload.
- [ ] Дългосрочно Neighbor Info ingestion/time-series.
- [ ] Mesh topology graph с direction, SNR и last-heard.
- [ ] Nodes-per-hop и congestion/local-stats dashboards.
- [ ] Базова OpenStreetMap карта и waypoints.

## M4.1 — Connectivity and gateway diagnostics (приоритет пред картата)

- [x] Коректна семантика за local radio, implicit relay и destination ACK.
- [x] Компактна packet journey с confirmed/pending/failed/unknown етапи.
- [x] On-demand route observer matrix само за explicit opt-in, identity-verified
  TCP профили, с subprocess изолация, identity/channel/radio comparison,
  subject last-heard и ясно „доказва/не доказва“ обозначение.
- [ ] Passive packet-ID correlation през read-only gateway observers.
- [ ] Read-only MQTT observer, отделен от бъдещия MQTT proxy/publisher.
- [ ] Redacted diagnostic bundle и сравнение на Local Stats делти.

Критерий: операторът може да локализира последната потвърдена граница, без
MeshDesk да представя implicit ACK като end-to-end доставка.

## M5 — Fleet inventory foundation

- [ ] Стабилна device identity, независимо от transport.
- [ ] Persistent capability/firmware inventory за повече управлявани устройства.
- [ ] Tags и saved selections за управлявани устройства.
- [ ] Разделяне на `managed devices` от `subject nodes`.
- [ ] Operation plan, dry-run diff и audit log.
- [ ] Ограничена command queue с retry и stop policy.

Това е задължителната основа преди mass config.

## M6 — Single-device role profiles

- [ ] Версионирани профили с metadata и обяснение.
- [ ] Preview на всички засегнати секции.
- [ ] Snapshot/export преди прилагане.
- [ ] Apply върху едно локално или remote-admin устройство.
- [ ] Post-check на role, LoRa и reachability.
- [ ] Rollback, когато устройството остава достижимо.

Първата версия няма да променя region, channel keys или modem preset
автоматично.

## M7 — Mass NodeDB operations

- [ ] Multi-select на управлявани устройства.
- [ ] Отделен multi-select на nodes за favorite/ignore.
- [ ] Матрица „коя NodeDB × кой subject node“.
- [ ] Preview на броя admin packets и очакваното airtime.
- [ ] Последователно изпълнение с per-target ACK/NAK.
- [ ] Pause, resume, retry failed и export на резултата.

## M8 — Staged mass configuration

- [ ] Canary node.
- [ ] Batch size и inter-command delay.
- [ ] Автоматично спиране при N последователни грешки.
- [ ] Защита на текущото gateway устройство.
- [ ] Reachability check след всяка партида.
- [ ] Signed/versioned configuration bundles.
- [ ] Approval summary за чувствителни и destructive полета.

## По-късни специализирани модули

- Firmware OTA/DFU.
- MQTT client proxy.
- Discovery preset scanner и Mesh Beacon.
- Advanced map layers, geofence и RF site planning.
- Географска карта на чутите възли.
- Opt-in AI обяснение върху redacted deterministic diagnostic bundle.
- TAK gateway.

Тези функции не трябва да блокират основната надеждност и fleet safety.
