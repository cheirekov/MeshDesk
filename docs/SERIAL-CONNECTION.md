# USB Serial connection

MeshDesk използва `meshtastic-python` и транзитивната му `pyserial` зависимост
в Devbox/Docker средата. Не се инсталира Python пакет в host системата.

## Discovery и избор

Табът **USB Serial → Открий USB** използва същата Meshtastic port detection
логика като официалния Python клиент. За всеки кандидат се показват:

- текущият kernel port (`/dev/ttyACM*` или `/dev/ttyUSB*`);
- product/manufacturer, USB VID:PID и serial number, когато са налични;
- read/write достъпът на MeshDesk процеса;
- стабилен `/dev/serial/by-id/...` endpoint, когато udev го предоставя.

Stable path е предпочитан за connection profile и auto-reconnect. Номерът на
`ttyACM`/`ttyUSB` може да се промени след изключване, reboot или включване на
друго USB устройство.

## Linux permissions

При Devbox MeshDesk работи като текущия потребител. На повечето Linux системи
Serial портът е достъпен за групата `dialout` или `uucp`:

```bash
ls -l /dev/serial/by-id /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
id
```

Ако липсва достъп, добавянето към съответната група е системна промяна и не се
прави автоматично от MeshDesk. След такава промяна обикновено е нужен нов login.
Не използвай `chmod 777` върху Serial устройството.

`permission_denied` не стартира безкраен reconnect, защото повторните опити не
могат да поправят Linux правата. Извадено или рестартиращо се устройство се
класифицира като временен `device_not_found`/`connection_lost` и profile
auto-reconnect остава приложим.

## Docker

Docker не получава USB device автоматично. Предай само конкретния port, а не
цялата `/dev` директория. Примерен локален `compose.override.yaml`:

```yaml
services:
  meshdesk:
    devices:
      - /dev/ttyACM0:/dev/meshtastic0
```

След това избери `/dev/meshtastic0` в контейнера. При промяна на host kernel
порта override-ът трябва да се обнови; Devbox с `/dev/serial/by-id/...` е
по-удобният вариант за често разкачани устройства.

## Lifecycle и безопасност

Serial използва същите правила като TCP и BLE:

- Meshtastic handshake и зареждане на NodeDB преди статус `connected`;
- profile binding към потвърдения node ID;
- opt-in auto-reconnect с bounded backoff;
- ръчно **Прекъсни** отменя timer-ите;
- identity mismatch блокира свързването към подменено радио.

Serial port се отваря exclusive от `meshtastic-python`. Затвори CLI, Android
USB или друг процес, който вече държи същото устройство.
