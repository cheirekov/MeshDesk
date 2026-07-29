# MeshDesk documentation

Тази директория съдържа проектната и операторската документация, която е
по-подробна от краткото ръководство в основния `README.md`.

## Съдържание

- [Implementation roadmap](ROADMAP.md) — подредени етапи и критерии за
  завършеност.
- [Connection profiles](CONNECTION-PROFILES.md) — локално запазени TCP/BLE
  endpoints и граници за бъдещия auto-reconnect.
- [TCP mDNS discovery](TCP-DISCOVERY.md) — откриване на
  `_meshtastic._tcp.local.` без системни пакети.
- [Connection health](CONNECTION-HEALTH.md) — lifecycle states, timestamps и
  допустимост за бъдещ reconnect.
- [UI information architecture](UX-STRUCTURE.md) — правила за подреждане на
  основни, вторични и бъдещи fleet секции.
- [Android/Desktop parity backlog](ANDROID-PARITY-BACKLOG.md) — пълната опашка
  от сравнението с официалния клиент.
- [Role profiles](ROLE-PROFILES.md) — кога се използват основните Meshtastic
  роли и как ще бъдат превърнати в безопасни профили.
- [Mass operations](MASS-OPERATIONS.md) — архитектура и защитни механизми за
  групови NodeDB и configuration операции.

## Принцип

MeshDesk третира radio конфигурацията като инфраструктурна промяна, а не като
обикновено попълване на форма. Операции, които могат да прекъснат връзката или
да натоварят LoRa мрежата, трябва да имат:

1. проверка на capabilities и firmware;
2. preview на точната промяна;
3. snapshot за възстановяване, когато протоколът го позволява;
4. canary изпълнение върху един node;
5. последователно и ограничено изпращане през LoRa;
6. ACK/NAK и отделен резултат за всяка цел;
7. audit trail без записване на тайни.
