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

Обикновеният channel list никога не съдържа PSK. UI получава само състояние:
`unencrypted`, `default`, `simpleN` или `secret`. При изрично
**Покажи текущия PSK** локалният API връща Base64 стойността с `no-store`;
стойността не се audit-ва, не влиза в history и се изчиства при hide, смяна на
slot/tab, затваряне на Settings, скриване на browser прозореца или disconnect.

При запис операторът избира:

- **Запази текущия** — bytes полето не се променя;
- **Random AES-256** — препоръчителен за private channel;
- **Random AES-128** — по-кратък, но валиден secure key;
- **Meshtastic default** — публично известен ключ;
- **simple0–simple254** — compact markers за публично известни ключове;
- **Без криптиране**;
- **Custom** — 1/16/32-byte Base64 или `0x…`, с повторно въвеждане.

Random ключовете се генерират с Web Crypto CSPRNG и се показват като Base64
preview преди save. Има show/hide, regenerate, live size validation и copy.
Новият ключ трябва да се приложи отделно на всички участници. MeshDesk не го
записва в audit събитията, browser storage или encrypted chat history.

`default` и `simpleN` не са private: ключовете им са публикувани в Meshtastic
source и служат за public/test channels. Еднобайтовата стойност е protocol
marker, а не реален еднобайтов AES key.

## Граници на първата версия

- управлява директно свързаното радио;
- няма remote channel administration;
- няма Channel URL/QR import/export;
- няма explicit drag-and-drop reorder;
- преди запис има confirmation, но пълният snapshot/rollback предстои.

Тези функции остават в M2 roadmap-а.
