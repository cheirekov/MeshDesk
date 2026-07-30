# Channel Manager

MeshDesk управлява Meshtastic `ChannelSettings` от таба **Настройки → Primary и
Secondary канали**, отделно от protobuf radio/module формата. Channel slot-овете
определят разговорите, PSK и MQTT uplink/downlink поведението.

## Правила

- slot `0` винаги остава `PRIMARY`;
- останалите активни slots са `SECONDARY`;
- нов Secondary се добавя само в първия свободен slot, за да няма
  non-contiguous channel layout;
- премахването използва стандартния `deleteChannel()` lifecycle на Meshtastic;
- името е до 10 знака и трябва да е уникално сред активните channels;
- position precision е между 0 и 32 bits.

## PSK handling

MeshDesk никога не връща съществуващия PSK към браузъра. UI получава само
състояние: `unencrypted`, `default`, `simpleN` или `secret`.

При запис операторът избира:

- **Запази текущия** — bytes полето не се променя;
- **Нов random 256-bit** — генерира се локално от Meshtastic Python;
- **Meshtastic default**;
- **Без криптиране**;
- **Custom** — 16/32-byte `0x…` или `base64:…`.

Новият ключ трябва да се приложи отделно на всички участници. MeshDesk не го
записва в audit събитията и не го връща в API response.

## Граници на първата версия

- управлява директно свързаното радио;
- няма remote channel administration;
- няма Channel URL/QR import/export;
- няма explicit drag-and-drop reorder;
- преди запис има confirmation, но пълният snapshot/rollback предстои.

Тези функции остават в M2 roadmap-а.
