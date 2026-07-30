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

## Administration

Всяка административна операция има отделен tooltip, който обяснява:

- какво се запазва и какво се изтрива;
- дали връзката ще прекъсне;
- разликата между NodeDB reset, config reset и full factory reset;
- ограниченията на remote PKI administration;
- кога favorite/ignore списъците могат да бъдат възстановени.

Destructive операциите продължават да използват постоянен warning и explicit
confirmation. Tooltip не е единствената защита.

## Sources

Описанията следват текущата official Meshtastic документация за
[Device](https://meshtastic.org/docs/configuration/radio/device/),
[Display](https://meshtastic.org/docs/configuration/radio/display/),
[Power](https://meshtastic.org/docs/configuration/radio/power/),
[LoRa](https://meshtastic.org/docs/configuration/radio/lora/) и
[Security](https://meshtastic.org/docs/configuration/radio/security/).

Tooltip interaction моделът следва
[Carbon](https://carbondesignsystem.com/components/tooltip/usage/) и
[Fluent 2](https://fluent2.microsoft.design/components/web/react/core/tooltip/usage).
