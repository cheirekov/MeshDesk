# Firmware and capability preflight

MeshDesk използва `DeviceMetadata`, върната от Meshtastic firmware, за да
провери дали конфигурационна или административна операция е приложима към
конкретното устройство. Проверката е свързана с Meshtastic node identity, а не
с TCP, BLE или USB endpoint-а.

## Източник на данните

- За локалното радио metadata идва от нормалния connection handshake.
- За избран remote-admin възел операторът стартира **Провери възможностите**.
  Това е отделна PKI admin заявка по mesh-а и подлежи на обичайните LoRa
  ограничения, ACK/NAK и timeout.
- Remote резултатът се пази само за текущата сесия. Бъдещият fleet inventory
  ще добави persistent timestamp, refresh policy и сравнение между устройства.

Показват се firmware version, device-state version, hardware model, role,
position flags, feature flags и firmware modules, изключени при build-а.

## Честен модел на състоянията

Capability има едно от три състояния:

- `supported` — firmware metadata потвърждава възможността;
- `unsupported` — metadata изрично я отхвърля;
- `unknown` — протоколът не предоставя достатъчно информация.

MeshDesk блокира изпращането само при `unsupported`. При `unknown` показва
предупреждение, но оставя утвърдената protocol операция достъпна. Версията на
firmware не се сравнява с ръчно поддържан списък и от нея не се отгатват
възможности.

## Прилагане

- `canShutdown = false` блокира software shutdown.
- `hasPKC = false` блокира remote-admin операция към този target.
- Битовете в `excluded_modules` блокират запис към съответната module config
  секция, например MQTT, Telemetry или Neighbor Info.
- Core radio config остава налична, когато metadata е получена.
- Секции без protocol capability bit са `unknown`, а не автоматично
  `supported` или `unsupported`.

В **Конфигурация** неподдържаната секция е видима за диагностика, но полетата и
записът са деактивирани. В **Администрация** target card показва текущия
preflight и забранява само доказано несъвместимите действия. Всеки изпратен
request и резултат запазва preflight контекста в session audit events, без
ключове или други тайни.

## Граница на тази стъпка

Това е safety preflight за едно свързано радио и за изрично проверени
remote-admin targets. Не е още fleet inventory, firmware updater или гаранция,
че хардуерът ще изпълни команда след ACK. Такива операции ще изискват snapshot,
preview, per-target result и post-check.
