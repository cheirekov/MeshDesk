# Connection profiles

Connection profiles са основата на M1 connection lifecycle. Те намаляват
ръчното въвеждане и са единственият начин да се включи автоматичен reconnect.

## Какво се пази

- операторско име;
- transport: TCP, BLE или USB Serial;
- TCP host и port, BLE address или explicit Serial `/dev` path;
- време на създаване, промяна и последно използване.
- потвърден Meshtastic node ID, име и време на последната identity проверка.
- explicit `auto_reconnect` opt-in.
- explicit `diagnostic_observer` opt-in само за TCP профили.

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
- След успешния handshake профилът се свързва с node ID на радиото.
- Следваща връзка към същия endpoint, но с различен node ID, показва mismatch и
  не променя запазената идентичност.
- „Приеми новото радио“ изисква отделно потвърждение и се използва само при
  умишлена смяна на устройството или identity reset.
- Auto-reconnect не е включен по подразбиране и се редактира от modal-а на
  профила.
- Route диагностиката също е opt-in: само identity-verified TCP профил може да
  бъде избран като наблюдател. Изборът се управлява от секцията
  „Наблюдатели на маршрута“ или от modal-а на профила.
- Ръчно въведен endpoint никога не стартира безкраен background retry.

## Reconnect policy

При `connection_lost`, timeout, отказан TCP endpoint, липсваща BLE реклама или
временно липсващ Serial device се използва `5, 10, 20, 40, 60 s` backoff.
След десет секунди стабилна сесия failure counter-ът се нулира. За BLE всеки
автоматичен опит прави fresh scan и само един GATT/handshake цикъл; следващият
се управлява от общия backoff.

BLE transport state се наблюдава локално през BlueZ/Bleak. Това позволява
рестартът на радиото да бъде засечен, без да се разчита на входящ mesh трафик и
без да се изпращат допълнителни радио пакети.

Loop-ът се блокира при:

- `pairing_required`;
- `permission_denied` за Serial device;
- identity mismatch спрямо потвърдения node ID;
- ръчно **Прекъсни** или endpoint switch.

Докато loop-ът е активен, съществуващият бутон **Прекъсни** остава достъпен.
Чатовете и последният NodeDB изглед остават видими като локален snapshot, но
изпращането и конфигурационните действия са disabled до успешен handshake.
