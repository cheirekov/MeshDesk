# Delivery and gateway diagnostics

MeshDesk използва evidence-first модел: показва като потвърден само етап, за
който има packet наблюдение. Липсващото наблюдение се означава като
**неизвестно**, а не като успех или повреда.

## Значение на статусите

| Статус | Какво е доказано | Какво не е доказано |
|---|---|---|
| В радио опашката | заявката чака свободен TX slot | че радиото вече е излъчило |
| Предадено на радиото | Meshtastic API е приел заявката | LoRa приемане от друг възел |
| LoRa relay чут | при broadcast е получен implicit ACK от чуто препредаване | channel decode, конкретен relay, gateway, MQTT или downstream доставка |
| Получателят потвърди | адресираният node е върнал destination ACK | какъв е бил целият маршрут |
| NAK | routing слой е върнал грешка | че повторен опит няма да успее |
| Timeout | очакваното потвърждение не е наблюдавано навреме | абсолютна гаранция, че никой не е получил пакета |

Чатът използва кратки етикети `↗ Relay` и `✓ Доставено`, за да не разширява
балончетата. Пълното значение остава в tooltip и Packet Inspector.

При старите history записи успешният broadcast може да е записан като
`delivered`. UI го нормализира до **LoRa relay чут**, когато destination е
`^all`, без да променя криптирания оригинал.

## Packet Inspector

За изходящо съобщение Inspector-ът показва компактна верига:

1. приемане от локалното радио;
2. broadcast relay или destination ACK;
3. gateway/MQTT broker observation;
4. downstream client observation.

Първите два етапа използват наличния Meshtastic response. Последните два са
**неизвестни**, докато MeshDesk няма независим observer за същия packet ID.
Implicit ACK никога не се използва като заместител на MQTT потвърждение.

`via_mqtt` върху входящ пакет доказва, че пакетът е минал през MQTT някъде по
пътя. Той не доказва кой gateway го е публикувал и не доказва симетричен uplink
маршрут за локалното радио.

## Следващи приоритетни етапи

1. **Route observer matrix** — реализирана като explicit on-demand проверка само
   на identity-verified TCP профили, които операторът е маркирал като
   диагностични наблюдатели: identity, last-heard, channel/region/modem
   съвместимост и UDP/MQTT състояние. Обикновен connection profile не участва
   автоматично. Probe-ът е изолиран subprocess с timeout, не извършва writes и
   не връща PSK/signatures към браузъра. NodeDB last-heard не доказва, че
   конкретен packet е минал през наблюдателя.
2. **Read-only profile observers** — реализирана bounded корелация на packet ID
   между основното радио и изрично избрани TCP наблюдатели. Началният TCP packet
  burst се оттича преди статус `ready`; след това се събират само metadata за
  пакети от активния subject, без text payload и configuration writes.
  Profile selection и активна observer сесия са отделни състояния. Composer
  показва ненатрапчив countdown, а Inspector различава `not configured`,
  `not armed`, `syncing/not ready`, `expired`, `armed but not seen` и
  `observed`. Първото sighting за observer+packet се пази като redacted,
  криптирано history evidence и остава достъпно след края на сесията.
3. **Read-only MQTT observer** — subscription и packet correlation без publish.
4. **Redacted diagnostic bundle** — export на фактите и времевата линия без
   PSK, private keys, credentials, текстове и точна позиция по подразбиране.

AI обяснение и географска карта са `nice to have`. Те не са зависимост за
надеждната диагностика и не трябва да интерпретират липсващи наблюдения като
факти.

Meshtastic API не multiplex-ва надеждно няколко receive клиента. Затова
матрицата не държи постоянни вторични връзки, а packet observer-ът има изричен
30–300 секунден lifecycle, identity guard и Stop действие. Observer evidence
доказва, че конкретният TCP възел е видял packet ID. Само `via_mqtt=true`
доказва MQTT входящ път към този наблюдател; LoRa/local sighting не доказва
broker publish.
