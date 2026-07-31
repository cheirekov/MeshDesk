# Connection health and liveness

MeshDesk разделя transport състоянието от радио активността. Липсата на
приети mesh пакети не означава автоматично повредена връзка.

## Health states

| State | Значение |
|---|---|
| `idle` | Няма започвана или запазена сесия |
| `connecting` | TCP/BLE transport и Meshtastic handshake се установяват |
| `reconnecting` | Автоматичен reconnect опит и handshake |
| `healthy` | Клиентската transport сесия е активна |
| `lost` | Активна сесия е прекъсната неочаквано |
| `failed` | Transport или handshake не са успели |
| `disconnected` | Операторът е прекъснал или сменил endpoint |

## Причини за прекъсване

Backend-ът пази отделни codes за:

- `manual` и `switch`;
- `timeout` и `connection_refused`;
- `device_not_found`, `pairing_required` и `identity_mismatch`;
- `connection_failed` и `connection_lost`.

Само временните transport грешки са маркирани като `reconnect_eligible`.
Ръчно прекъсване, endpoint switch и pairing проблем не трябва да стартират
автоматичен loop.

## Reconnect state

`health.reconnect` съдържа:

- `enabled` — opt-in политиката на избрания запазен профил;
- `active` и `phase`: `armed`, `waiting`, `connecting`, `stabilizing` или
  `blocked`;
- номер на опита, оставащи секунди и точен `next_at` timestamp;
- последен опит, последен успех, block reason и максимален delay.

Backoff-ът е ограничен до `5 → 10 → 20 → 40 → 60 s` и не изпраща LoRa
пакети. Stable transport сесия от 10 секунди нулира failure counter-а. Това
избягва агресивни BLE/GATT цикли, но позволява power-save устройство да бъде
намерено, когато отново започне да рекламира.

## Timestamps

Health payload съдържа:

- начало на connect опита и успешната сесия;
- последна protocol активност;
- последен приет пакет;
- край или загуба на сесията;
- последен transport и endpoint.

`last_activity_at` включва успешно изпратени/получени protocol операции.
`last_rx_at` е по-тесен сигнал само за получени пакети.

## Ограничение

MeshDesk не изпраща периодични LoRa пакети само за health проверка. Това би
увеличило airtime и не би било коректен тест на локалния TCP/BLE transport.
Загубата се отчита от самия interface, а тихата mesh мрежа остава `healthy`.
