# Professional mass operations

Mass operations са бъдещ fleet слой на MeshDesk. Те не са просто цикъл върху
съществуващия API.

## Два различни вида селекция

UI трябва ясно да разделя:

1. **Managed devices** — устройствата, чиито NodeDB/config ще бъдат променени.
2. **Subject nodes** — nodes, които ще бъдат favorite/ignored или използвани в
   друга NodeDB операция.

Пример: 4 managed routers × 6 subject nodes за favorite означава план от 24
admin операции. MeshDesk трябва да покаже това число преди изпълнение.

## Operation lifecycle

1. **Inventory refresh** — firmware, capabilities, last heard, PKI access.
2. **Selection validation** — премахване на unreachable/unauthorized targets.
3. **Plan** — точен списък от команди без изпращане.
4. **Dry run** — diff, packet count, риск и очакван airtime.
5. **Snapshot** — export на наличната конфигурация, когато може да бъде прочетена.
6. **Canary** — една избрана цел.
7. **Post-check** — ACK/NAK и повторно прочитане на променената стойност.
8. **Batches** — малки последователни групи.
9. **Stop policy** — автоматично спиране при загуба на gateway или поредица от
   грешки.
10. **Report** — success/failed/skipped/unknown за всяка цел.

## LoRa ограничения

- Remote admin командите се изпращат последователно, не паралелно.
- Между командите има configurable delay.
- Операциите имат дневен/сесиен packet budget.
- MeshDesk не retry-ва безкрайно.
- Retry на non-idempotent или destructive команда изисква отделно решение.
- Channel, LoRa, network и Bluetooth промени се изпълняват последни, защото
  могат да прекъснат управлението.

## Favorite/ignore

Тези операции са добър първи mass workflow, защото са тесни и обратими:

- `favorite` ↔ `unfavorite`;
- `ignore` ↔ `unignore`.

Въпреки това remote NodeDB не може да бъде изтеглена изцяло със стандартния
admin протокол. Затова резултатът трябва да различава:

- командата е ACK-ната;
- desired state е потвърден чрез последващо четене;
- desired state не може да бъде прочетен и остава „accepted, unverified“.

## Mass configuration

Пълният mass config идва след NodeDB workflow и single-device profiles.

Задължителни защити:

- забранени тайни в audit/export;
- explicit allow-list на полетата в bundle-а;
- firmware-aware schema;
- preview на всички implicit промени;
- защита срещу едновременно сменяне на preset/channel на gateway и targets;
- canary и rollback инструкции;
- подпис/хеш и версия на bundle-а;
- operator identity и timestamp в audit report.
