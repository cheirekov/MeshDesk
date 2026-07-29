# Connection profiles

Connection profiles са първата реализация от M1. Те намаляват ръчното
въвеждане, но все още не правят автоматично reconnect.

## Какво се пази

- операторско име;
- transport: TCP или BLE;
- TCP host и port, или BLE address;
- време на създаване, промяна и последно използване.

Не се пазят Bluetooth PIN, channel PSK, Wi-Fi парола, private/admin keys или
друга radio конфигурация.

Профилите се записват атомарно в `logs/connection-profiles.json` с файлови
права `0600`. `logs/` е локална и е изключена от Git. Docker конфигурацията
вече монтира същата директория като persistent volume.

## Поведение в интерфейса

Профилите са в горната карта „Връзка“, защото принадлежат към connection
lifecycle, а не към firmware конфигурацията на радиото.

- „Ръчно въвеждане“ не променя запазен профил.
- Избор на профил попълва transport и endpoint.
- Ръчна промяна след избора се показва като незаписана.
- Връзка с незаписана промяна не обновява `last_used_at` на стария профил.
- Изтриването премахва само локалния профил; не забравя BlueZ pairing.

## Следващи зависимости

Преди auto-reconnect към профила трябва да се добавят:

1. потвърдена Meshtastic device identity след handshake;
2. health state и причина за прекъсването;
3. explicit opt-in за auto-reconnect;
4. bounded exponential backoff и бутон за спиране.

Това предотвратява reconnect loop към грешен endpoint или устройство.
