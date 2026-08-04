# Fleet identity and access paths

Fleet inventory не е списък от TCP/BLE connection profiles. Основният обект е
**управляваното Meshtastic устройство**, идентифицирано чрез node ID и, когато е
наличен, неговия public key.

## Отделни обекти

### Managed device

Съдържа стабилната идентичност, операторско име, tags, firmware/capability
snapshot и последно потвърдено състояние. Устройството може да няма IP адрес,
Bluetooth връзка или USB endpoint.

### Access path

Едно устройство може да има повече от един път:

- direct TCP connection profile;
- direct BLE или USB profile;
- remote LoRa admin през локално controller радио;
- remote LoRa admin през алтернативен controller/gateway.

Remote LoRa пътят свързва target node ID с controller identity, channel и
потвърдена PKI admin capability. Той е transient: наличието на public/admin key
не е гаранция, че RF маршрутът е достъпен в момента.

### Diagnostic observer

Observer-ът е източник на evidence, а не автоматично access path и не
автоматично fleet member. TCP route observer може да види packet, без да има
право да администрира неговия source или destination.

### Operation

Fleet операцията адресира managed device, след което planner избира и показва
конкретния access path. Audit записът трябва да съдържа target identity,
controller identity, operation, dry-run diff, ACK/NAK/timeout и post-read
verification, но не и private keys или channel PSK.

## Задължителни правила

1. Липсата на direct endpoint не изключва устройство от fleet-а.
2. Favorite/ignore не означава admin capability.
3. „Admin key configured“ и „remote admin verified“ са различни състояния.
4. Mass operation не започва без capability preflight и избран access path за
   всяка цел.
5. Remote LoRa writes са bounded, последователни и с cooldown; няма паралелен
   flood към mesh-а.
6. Canary, explicit confirmation, stop policy и audit са задължителни преди
   масова конфигурация.

Този модел позволява един fleet да съдържа едновременно локални USB радиа,
Wi-Fi gateway-и и инфраструктурни възли, достижими единствено чрез LoRa PKI
administration.
