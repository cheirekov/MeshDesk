# Connection health and liveness

MeshDesk разделя transport състоянието от радио активността. Липсата на
приети mesh пакети не означава автоматично повредена връзка.

## Health states

| State | Значение |
|---|---|
| `idle` | Няма започвана или запазена сесия |
| `connecting` | TCP/BLE transport и Meshtastic handshake се установяват |
| `healthy` | Клиентската transport сесия е активна |
| `lost` | Активна сесия е прекъсната неочаквано |
| `failed` | Transport или handshake не са успели |
| `disconnected` | Операторът е прекъснал или сменил endpoint |

## Причини за прекъсване

Backend-ът пази отделни codes за:

- `manual` и `switch`;
- `timeout` и `connection_refused`;
- `device_not_found` и `pairing_required`;
- `connection_failed` и `connection_lost`.

Само временните transport грешки са маркирани като `reconnect_eligible`.
Ръчно прекъсване, endpoint switch и pairing проблем не трябва да стартират
автоматичен loop.

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
