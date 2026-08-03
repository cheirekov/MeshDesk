# Channel Manager

MeshDesk управлява Meshtastic `ChannelSettings` от таба **Настройки → Primary и
Secondary канали**, отделно от protobuf radio/module формата. Channel slot-овете
определят разговорите, PSK и MQTT uplink/downlink поведението.

## Правила

- slot `0` винаги остава `PRIMARY`;
- останалите активни slots са `SECONDARY`;
- нов Secondary се добавя само в първия свободен slot, за да няма
  non-contiguous channel layout;
- локалното премахване използва стандартния `deleteChannel()` lifecycle;
- remote премахването пресъздава същото преместване на следващите slots и ги
  записва последователно с отделен ACK;
- името е до 10 знака и трябва да е уникално сред активните channels;
- position precision е между 0 и 32 bits.

Device role (`CLIENT`, `CLIENT_MUTE`, `CLIENT_BASE`, `ROUTER` и др.) не
ограничава броя или вида на channel slots. Тя променя transport/routing и
rebroadcast поведението. Channel role (`PRIMARY`, `SECONDARY`, `DISABLED`) е
отделна protobuf настройка.

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

Token-ът е свързан и с managed target-а. Preview за локалното радио не може да
се приложи към remote node и обратно.

При потвърждение token-ът се консумира. Променена форма, изтекъл token или
channel state, различен от прегледания, отказват write и изискват нов preview.
Точно преди write се създава пълен protobuf snapshot на всички slots. Той
съдържа PSK bytes, затова се пази отделно като
`logs/<node-id>.channel-backups.aes`, криптиран с AES-GCM и локалния MeshDesk
history key. Backup ID влиза в audit резултата, но съдържанието и ключовете не.

Snapshot restore UI предстои; дотогава backup-ът е recovery artifact, а не
автоматичен rollback.

## Remote channels през LoRa

От **Управлявано устройство** се избира PKI-admin node. MeshDesk не зарежда
каналите автоматично: бутонът **Зареди през LoRa** изпраща осем последователни
`get_channel_request` заявки. Така скъпият LoRa трафик остава изрично действие
и UI показва pending/success/error резултат.

Изисквания:

- локалният public key е разрешен в `security.admin_key` на target-а;
- target-ът е достижим по mesh-а и firmware-ът поддържа PKI admin;
- gateway връзката остава активна до края на заявката/записа.

При save MeshDesk:

1. прави capability preflight и target-bound preview;
2. записва encrypted snapshot под identity-то на remote node-а, с
   `managed_via` идентичността на gateway радиото;
3. изпраща всеки засегнат `set_channel` последователно;
4. различава ACK, NAK и timeout и подновява session key еднократно при
   `ADMIN_BAD_SESSION_KEY`;
5. прочита отново засегнатите slots и съобщава `verified`, `mismatch` или
   `unavailable`.

Промяната на PRIMARY име/PSK може да смени frequency slot-а или достъпния ключ
и target-ът да стане недостижим веднага след прилагането. Това не е безопасно
за mass operation; първо трябва canary върху един физически достъпен node.

## Оставащи граници

- няма Channel URL/QR import/export;
- няма explicit drag-and-drop reorder;
- encrypted snapshot се създава, но restore/rollback UI предстои.

Тези функции остават в M2 roadmap-а.
