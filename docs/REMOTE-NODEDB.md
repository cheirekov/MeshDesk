# Remote NodeDB favorite/ignore

Favorite и ignore са свойства на конкретна NodeDB, а не глобални свойства на
mesh node. Затова всяка операция има две отделни роли:

- **subject node** — възелът, който се добавя/премахва от favorite или ignore;
- **managed node** — радиото, чиято NodeDB се променя.

Пример: когато MeshDesk е свързан към `nodeX`, в Inspector е отворен `node1`, а
в **Промени NodeDB на** е избран `node2`, командата означава:

> промени NodeDB на `node2`, така че subject `node1` да бъде favorite/ignored.

Favorite/ignore флаговете, получени при връзката към `nodeX`, описват само
NodeDB на `nodeX`. Те не доказват състоянието на `node2`.

## Поведение в интерфейса

При **Локално** MeshDesk знае текущите флагове и показва един контекстен бутон
за favorite и един за ignore.

При **Remote** стандартният Meshtastic admin протокол не предоставя операция за
изтегляне на цялата чужда NodeDB. Затова MeshDesk:

1. показва `Remote състояние: неизвестно`;
2. показва отделни, недвусмислени **Добави** и **Премахни** действия;
3. иска потвърждение с managed и subject node;
4. изпраща PKI admin командата последователно;
5. различава `ACK`, `NAK` и `timeout`;
6. пази резултата в локалния encrypted audit log.

`ACK` означава, че remote устройството е приело командата. Той не е read-back
потвърждение на desired state, затова резултатът е `accepted, unverified`.
`NAK` съдържа protocol причина, например липсващо admin разрешение. При timeout
MeshDesk не твърди, че desired state е променен; повторението остава изрично
решение на оператора.

При `ADMIN_BAD_SESSION_KEY` MeshDesk изтрива само кеширания session passkey за
managed node, заявява нов ключ и повтаря обратимата favorite/ignore команда
точно веднъж. Други NAK причини не се retry-ват автоматично. Audit резултатът
показва, когато admin сесията е била подновена.

Favorite/ignore за самото managed радио не е валидна operator операция:
собственият запис не се управлява като remote peer и не може да бъде evicted или
ignored по този начин. MeshDesk означава такъв запис като **собствено радио**,
скрива preference бутоните и отхвърля директна API заявка.

## Изисквания

- публичният ключ на gateway радиото трябва да присъства в
  `security.admin_key` на managed remote node;
- managed node трябва да е достижим през mesh-а;
- firmware-ът трябва да поддържа съответната AdminMessage команда.

Този единичен workflow е основата за бъдещата mass матрица
`managed NodeDB × subject nodes`, но не предполага, че remote state може да
бъде прочетен.
