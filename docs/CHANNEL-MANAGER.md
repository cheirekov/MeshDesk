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
reveal отговорът не се audit-ва, не влиза в chat history и се изчиства при
hide, смяна на slot/tab, затваряне на Settings, скриване на browser прозореца
или disconnect. Единственото съхранение на PSK е криптираният pre-write backup,
описан по-долу.

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
записва в plaintext audit събитията, browser storage или encrypted chat history.
Той присъства единствено в отделния encrypted pre-write backup, необходим за
бъдещо възстановяване.

`default` и `simpleN` не са private: ключовете им са публикувани в Meshtastic
source и служат за public/test channels. Еднобайтовата стойност е protocol
marker, а не реален еднобайтов AES key.

## Preview и backup преди write

**Запиши channel** първо изпраща параметрите към preview endpoint. Backend-ът:

1. прилага същата validation логика като реалния write;
2. връща diff без PSK bytes;
3. добавя предупреждения за public/open PSK, MQTT и slot deletion;
4. издава еднократен token с петминутен срок, свързан с request digest и
   fingerprint на всички текущи channel slots.

При потвърждение token-ът се консумира. Променена форма, изтекъл token или
channel state, различен от прегледания, отказват write и изискват нов preview.
Точно преди write се създава пълен protobuf snapshot на всички slots. Той
съдържа PSK bytes, затова се пази отделно като
`logs/<node-id>.channel-backups.aes`, криптиран с AES-GCM и локалния MeshDesk
history key. Backup ID влиза в audit резултата, но съдържанието и ключовете не.

Snapshot restore UI предстои; дотогава backup-ът е recovery artifact, а не
автоматичен rollback.

## Оставащи граници

- управлява директно свързаното радио;
- няма remote channel administration;
- няма Channel URL/QR import/export;
- няма explicit drag-and-drop reorder;
- encrypted snapshot се създава, но restore/rollback UI предстои.

Тези функции остават в M2 roadmap-а.
