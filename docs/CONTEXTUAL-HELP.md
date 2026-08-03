# Contextual Help

MeshDesk използва малка `i` икона непосредствено до функцията, която обяснява.
Tooltip-ът се отваря при hover, click, `Tab` focus и `Enter`/`Space`, а `Escape`
го затваря. Текстът е supplemental: бутоните, имената и критичните
предупреждения трябва да остават разбираеми и без него.

## Configuration registry

Field-level registry описва познатите полета от текущата Meshtastic protobuf
схема:

- предназначение и мерна единица;
- зависимост от конкретен GPIO, sensor или display хардуер;
- ефект върху airtime, power и privacy;
- риск от прекъсване на BLE, TCP или LoRa reachability;
- безопасен default или recovery препоръка, когато има такава.

Непознато поле от по-нов firmware не остава без помощ. Type-aware fallback
разпознава secret/read-only полета, GPIO/pin, time interval, boolean и enum
стойности. Това не замества capability validation, но предупреждава оператора
да провери firmware и хардуера.

Полета със специална числова семантика получават и live ред **Текущо**:

- секундите се превеждат в минути/часове/дни;
- `0 = disabled` се изписва като състояние, а не само като число;
- комбинируемите bitmask флагове се декодират, като неизвестните bits се
  запазват и означават, вместо да бъдат отхвърляни;
- channel/traffic position precision се показва като privacy зона;
- enum опциите имат четим label, но пазят точния protocol token след него.

Hardware-зависими GPIO, calibration и power-monitor debug bits нямат измислен
универсален range. Help насочва към pinout/firmware на точната платка и
препоръчва запазване на текущата стойност.

## Telemetry semantics

`battery_level` от 0 до 100 е процент. Стойност над 100 е официалният
Meshtastic marker за външно захранване и се показва като `⚡ външно`, без да се
прави недоказан извод за зарядно, USB, solar или charging state.

Metric таблиците премахват известните представяния на едно и също protobuf
поле (`camelCase`/`snake_case`, integer и derived GPS координати) и не повтарят
вложения `raw` object. Няма общо dedup по еднаква стойност, защото два различни
сензора могат легитимно да отчетат едно и също число. Пълните telemetry и
position payload-и остават достъпни в затворен по подразбиране Raw panel.

## Administration

Всяка административна операция има отделен tooltip, който обяснява:

- какво се запазва и какво се изтрива;
- дали връзката ще прекъсне;
- разликата между NodeDB reset, config reset и full factory reset;
- ограниченията на remote PKI administration;
- кога favorite/ignore списъците могат да бъдат възстановени.

Destructive операциите продължават да използват постоянен warning и explicit
confirmation. Tooltip не е единствената защита.

## Channel PSK

Channel editor-ът показва PSK само при изрично действие:

- новият random/custom ключ има masked Base64 preview, reveal и copy;
- custom стойността се валидира при писане и се въвежда повторно;
- текущият записан ключ се зарежда с отделен `no-store` request;
- стойността не се пази в local/session storage, plaintext audit или chat
  history; pre-write backup-ът я съдържа само в AES-GCM криптиран protobuf;
- hide, смяна на slot/tab, затваряне/скриване и disconnect премахват стойността
  от UI.

AES-256 и AES-128 са private варианти. `default` и `simple0–simple254` са
публично известни keys за public/test channels, а `none` не използва
криптиране.

## Sources

Описанията следват текущата official Meshtastic документация за
[Device](https://meshtastic.org/docs/configuration/radio/device/),
[Display](https://meshtastic.org/docs/configuration/radio/display/),
[Power](https://meshtastic.org/docs/configuration/radio/power/),
[LoRa](https://meshtastic.org/docs/configuration/radio/lora/) и
[Security](https://meshtastic.org/docs/configuration/radio/security/).
Battery sentinel и field единиците следват official
[Telemetry protobuf](https://github.com/meshtastic/protobufs/blob/master/meshtastic/telemetry.proto),
а privacy зоните следват official
[Channel position precision](https://meshtastic.org/docs/configuration/radio/channels/#position-precision).

Tooltip interaction моделът следва
[Carbon](https://carbondesignsystem.com/components/tooltip/usage/) и
[Fluent 2](https://fluent2.microsoft.design/components/web/react/core/tooltip/usage).
