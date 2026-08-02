# MeshDesk implementation roadmap

Roadmap-ът разделя обикновения Linux клиент от бъдещия professional/fleet слой.
Редът е умишлен: първо надеждност и наблюдаемост, след това масови промени.
Пълният inventory от Android сравнението е в
[`ANDROID-PARITY-BACKLOG.md`](ANDROID-PARITY-BACKLOG.md).

## M0 — Documentation and guidance

Статус: **в процес**

- [x] Отделна документационна структура.
- [x] Role Advisor за `CLIENT`, `CLIENT_BASE`, `CLIENT_MUTE`, `ROUTER` и
  `ROUTER_LATE`.
- [x] Contextual help за чувствителни configuration секции.
- [x] Field-level help за radio/module/channel настройки и Administration.
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
- [ ] Preview и backup преди запис.
- [ ] Remote channel administration при поддържан firmware.

Критерий: каналите могат да се управляват безопасно, без CLI или Android.

## M3 — Professional messaging

- [ ] Реален `reply_id` и quoted reply.
- [ ] Emoji reactions.
- [ ] Пълни routing/delivery състояния и човешки обяснения.
- [x] Честен queued → radio/enroute → ACK/NAK/timeout lifecycle.
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
- [ ] Дългосрочно Neighbor Info ingestion/time-series.
- [ ] Mesh topology graph с direction, SNR и last-heard.
- [ ] Nodes-per-hop и congestion/local-stats dashboards.
- [ ] Базова OpenStreetMap карта и waypoints.

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
- TAK gateway.

Тези функции не трябва да блокират основната надеждност и fleet safety.
