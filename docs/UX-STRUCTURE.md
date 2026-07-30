# UI information architecture

MeshDesk подрежда секциите според честота, риск и момент на употреба.

## Основен работен поток

1. **Връзка** — винаги първа; след свързване се свива до status bar.
2. **Съобщения** — основната ежедневна работа.
3. **Мрежа** — nodes, diagnostics и действия към конкретен node.

## Вторични секции

4. **Диагностика** — read-only и сгъната по подразбиране.
5. **Настройки** — рядко използвана и сгъната; съдържа табове **Radio и
   модули** и **Primary и Secondary канали**.
6. **Администрация** — последна, сгъната и визуално отделена заради reset,
   shutdown и factory-reset операциите.

## Контекстна помощ

Помощта не е самостоятелна карта в основния поток. Краткото обяснение стои до
полето, което засяга, а подробното сравнение се отваря при поискване.

Кратката supplemental помощ използва `i` trigger и floating tooltip:

- работи при hover и keyboard focus;
- свързва се чрез `aria-describedby`;
- не съдържа бутони или други интерактивни елементи;
- не съдържа критична информация, необходима за завършване на операцията;
- позиционира се във viewport, а не вътре в scroll container.

Критичните предупреждения остават като постоянно helper text. Решението следва
[Carbon tooltip guidance](https://carbondesignsystem.com/components/tooltip/usage/)
и [Fluent 2 tooltip guidance](https://fluent2.microsoft.design/components/web/react/core/tooltip/usage).

Field-level registry покрива познатите radio/module/channel параметри с
предназначение, единица и risk context. Ново protobuf поле получава fallback
според `secret`, `read_only`, GPIO, interval, boolean или enum типа, докато бъде
добавено специализирано описание. Подробности:
[Contextual Help](CONTEXTUAL-HELP.md).

Затова Role Advisor се показва в `Configuration → Device → role`, а не между
диагностиката и административните операции. Диалогът:

- не променя стойности;
- връща focus към бутона, който го е отворил;
- може да бъде затворен с Escape или чрез ясно означен бутон;
- пази предупрежденията видими само когато са релевантни.

## Бъдещи professional секции

Fleet inventory и Operations Center няма да бъдат добавени като още големи
карти в края на страницата. Когато станат достатъчно функционални, те трябва да
получат отделна top-level навигация:

- **Workspace** — chat и текущо радио;
- **Network** — nodes, topology и telemetry;
- **Fleet** — managed devices, selections и operation plans;
- **Settings** — локални предпочитания и документация.

Това преминаване има смисъл след stable device identity и operation planner,
не преди тях.
