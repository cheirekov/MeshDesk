# TCP mDNS discovery

MeshDesk открива native Meshtastic TCP endpoints чрез DNS-SD service
`_meshtastic._tcp.local.`. Firmware и Linux-native `meshtasticd` обикновено
публикуват service port `4403`.

## Употреба

1. отвори картата „Връзка“;
2. избери `TCP / Wi-Fi`;
3. натисни „Открий“;
4. избери резултат и натисни „Използвай“;
5. при желание запази endpoint-а като connection profile.

Discovery не стартира връзка автоматично и не променя запазен профил без
операторско действие.

За всеки резултат MeshDesk показва публикуваните:

- service name, hostname, IP адреси и TCP port;
- node ID, short name и firmware platform от TXT metadata, когато са налични;
- MAC адрес от TXT или локалния Linux neighbor/ARP cache;
- verified long name и profile name, ако node ID вече съвпада със запазен
  connection profile.

Meshtastic long name обикновено не е част от mDNS TXT записа. MeshDesk не
отваря скрити TCP сесии към всички резултати, защото радиото може да допуска
само един клиент. Long name се научава безопасно при изрично свързване и
успешен handshake.

## Изолация

Реализацията използва Python `zeroconf`, деклариран в `pyproject.toml` и
заключен в `uv.lock`. Не изисква инсталиране на `avahi-utils`, Bonjour или друг
системен пакет.

При Docker multicast discovery изисква host networking. Съществуващият
`docker-compose.yml` вече използва този режим. VLAN segmentation, client
isolation и firewall правила могат да блокират mDNS дори когато директната TCP
връзка работи.
