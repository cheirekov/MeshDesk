const state = {
  transport: "tcp",
  connection: "disconnected",
  lastError: null,
  lastEvent: 0,
  nodeRefreshAt: 0,
  configSections: [],
  activeConfig: null,
  nodes: [],
  channels: [],
  channelSlots: [],
  activeChannelSlot: null,
  unread: {},
  chatMessages: {},
  deliveryReceipts: {},
  selectedConversation: null,
  closedConversations: new Set(),
  sessionUiCleared: false,
  eventLog: [],
  inspector: null,
  profileId: null,
  connectionExpanded: true,
  connectionProfiles: [],
  connectionProfileDirty: false,
  connectionProfileModalId: null,
  connectionIdentityMismatch: null,
  discoveredTcpDevices: [],
  roleAdvisorTrigger: null,
  status: null,
  readThrough: Number(localStorage.getItem("meshdeskReadThrough") || 0) || 0,
};

const $ = (selector) => document.querySelector(selector);
const initializedHelpTriggers = new WeakSet();
const statusLabels = {
  disconnected: "Изключено",
  connecting: "Свързване…",
  connected: "Свързано",
  error: "Грешка",
};
const healthLabels = {
  idle: "Няма активна сесия",
  connecting: "Извършва се Meshtastic handshake",
  healthy: "Transport сесията е активна",
  lost: "Връзката беше неочаквано загубена",
  failed: "Свързването не успя",
  disconnected: "Връзката е прекъсната",
};
const disconnectReasonLabels = {
  manual: "Прекъснато от оператора",
  switch: "Endpoint-ът е сменен",
  timeout: "Изтече времето за свързване или handshake",
  connection_refused: "TCP endpoint-ът отказа връзката",
  device_not_found: "Устройството не е намерено или не рекламира",
  pairing_required: "Bluetooth сдвояването липсва или не е разрешено",
  connection_failed: "Transport-ът не успя да установи сесия",
  connection_lost: "Активната transport сесия беше прекъсната",
};

function organizeWorkspace() {
  const configuration = $("#configPanel");
  const administration = $("#adminPanel");
  if (configuration && administration) {
    administration.parentElement.insertBefore(configuration, administration);
  }
}

function clearCurrentChannelPskReveal() {
  const input = $("#channelCurrentPsk");
  if (!input) return;
  input.value = "";
  input.type = "password";
  const status = $("#channelCurrentPskStatus");
  if (status) {
    status.textContent = "Скрит по подразбиране.";
    status.className = "channel-psk-status";
  }
  const copyButton = $("#copyCurrentChannelPsk");
  if (copyButton) copyButton.disabled = true;
  const revealButton = $("#revealCurrentChannelPsk");
  if (revealButton) revealButton.textContent = "Покажи текущия PSK";
}

function selectSettingsView(view) {
  const channels = view === "channels";
  if (!channels) clearCurrentChannelPskReveal();
  $("#configSettingsView").classList.toggle("hidden", channels);
  $("#channelPanel").classList.toggle("hidden", !channels);
  $("#settingsConfigTab").classList.toggle("active", !channels);
  $("#settingsChannelsTab").classList.toggle("active", channels);
  $("#settingsConfigTab").setAttribute("aria-selected", String(!channels));
  $("#settingsChannelsTab").setAttribute("aria-selected", String(channels));
  $("#settingsConfigTab").tabIndex = channels ? -1 : 0;
  $("#settingsChannelsTab").tabIndex = channels ? 0 : -1;
  if (channels && state.connection === "connected") {
    Promise.all([refreshChannelSlots(), refreshChannels()]);
  }
}

function positionHelpTooltip(trigger) {
  const tooltip = $("#helpTooltip");
  const rect = trigger.getBoundingClientRect();
  const margin = 8;
  tooltip.textContent = trigger.dataset.help;
  tooltip.classList.remove("hidden");
  const tooltipRect = tooltip.getBoundingClientRect();
  let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
  left = Math.max(12, Math.min(left, window.innerWidth - tooltipRect.width - 12));
  let top = rect.bottom + margin;
  if (top + tooltipRect.height > window.innerHeight - 12) {
    top = rect.top - tooltipRect.height - margin;
  }
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(12, top)}px`;
}

function hideHelpTooltip() {
  $("#helpTooltip").classList.add("hidden");
}

function initHelpTips(root = document) {
  root.querySelectorAll("[data-help]").forEach((trigger) => {
    if (initializedHelpTriggers.has(trigger)) return;
    initializedHelpTriggers.add(trigger);
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      positionHelpTooltip(trigger);
    });
    trigger.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        positionHelpTooltip(trigger);
      }
    });
    trigger.addEventListener("mouseenter", () => positionHelpTooltip(trigger));
    trigger.addEventListener("mouseleave", hideHelpTooltip);
    trigger.addEventListener("focus", () => {
      trigger.setAttribute("aria-describedby", "helpTooltip");
      positionHelpTooltip(trigger);
    });
    trigger.addEventListener("blur", () => {
      trigger.removeAttribute("aria-describedby");
      hideHelpTooltip();
    });
  });
}

function relativeTime(value) {
  if (!value) return "—";
  const timestamp = new Date(value);
  const seconds = Math.max(0, Math.round((Date.now() - timestamp.getTime()) / 1000));
  let relative;
  if (seconds < 10) relative = "преди малко";
  else if (seconds < 60) relative = `преди ${seconds} сек`;
  else if (seconds < 3600) relative = `преди ${Math.floor(seconds / 60)} мин`;
  else if (seconds < 86400) relative = `преди ${Math.floor(seconds / 3600)} ч`;
  else relative = `преди ${Math.floor(seconds / 86400)} дни`;
  return `${timestamp.toLocaleString()} · ${relative}`;
}

function elapsedTime(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds} сек`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} мин`;
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)} ч ${Math.floor((seconds % 3600) / 60)} мин`;
  }
  return `${Math.floor(seconds / 86400)} дни`;
}

const roleGuidance = {
  CLIENT: {
    badge: "Препоръчителен default",
    className: "recommended",
    summary:
      "За повечето portable и ежедневно използвани устройства. Участва нормално в mesh-а и избягва ненужен relay, когато друг node вече е препредал пакета.",
    use: "Телефон/лаптоп gateway, handheld и общ Meshtastic node",
    power: "Батерия или постоянно захранване",
    relay: "Адаптивен, стандартен",
    caution: "Първият избор, освен ако измерена топология не налага специална роля.",
  },
  CLIENT_BASE: {
    badge: "База с избрани peers",
    className: "recommended",
    summary:
      "Фиксирана операторска база. При актуален firmware дава ROUTER_LATE-подобно подпомагане само за трафик от/към favorited nodes и остава CLIENT за останалите.",
    use: "Домашна база с кратък, умишлено подбран favorite списък",
    power: "Препоръчително постоянно",
    relay: "Приоритетно за favorites",
    caution: "Провери firmware capability и favorites преди прилагане.",
  },
  CLIENT_MUTE: {
    badge: "Без relay",
    className: "",
    summary:
      "Изпраща и получава собствен трафик, но не препредава чужди пакети. Намалява airtime в гъста мрежа.",
    use: "Monitoring endpoint, тестов node или много гъста локална мрежа",
    power: "Батерия или постоянно",
    relay: "Изключен",
    caution: "Не го използвай на node, който свързва две части на mesh-а.",
  },
  ROUTER: {
    badge: "Инфраструктура · висок ефект",
    className: "infrastructure",
    summary:
      "Винаги rebroadcast-ва и го прави възможно най-бързо. Подходящ само за стратегически разположена инфраструктура.",
    use: "Висока точка, добра антена, доказана нужда от backbone relay",
    power: "Постоянно и надеждно",
    relay: "Агресивен / винаги",
    caution: "Прекалено много ROUTER nodes увеличават collisions, queue pressure и duty-cycle.",
  },
  ROUTER_LATE: {
    badge: "Допълваща инфраструктура",
    className: "infrastructure",
    summary:
      "Rebroadcast-ва веднъж, но след по-ранните подходящи relays. Дава резервно покритие, без да се състезава първи.",
    use: "Supplemental coverage между clusters или резервен инфраструктурен node",
    power: "Постоянно и надеждно",
    relay: "Винаги, но отложено",
    caution: "Пак е инфраструктурна роля; наблюдавай utilization и relay counters.",
  },
};

const configSectionGuidance = {
  lora: {
    title: "LoRa: промяна с ефект върху цялата свързаност",
    warning: true,
    text: "Region, modem preset и channel параметрите определят дали nodes изобщо могат да се чуват.",
    bullets: [
      "Region трябва да съответства на физическото местоположение и регулацията.",
      "Preset трябва да е съвместим с останалата мрежа.",
      "Hop limit 3 е разумна начална стойност; по-голям не означава автоматично по-добър.",
    ],
  },
  security: {
    title: "Security: идентичност и remote-admin доверие",
    warning: true,
    text: "Промяна на identity/admin ключове може да смени node ID или да прекъсне remote достъпа.",
    bullets: [
      "Не споделяй private key и не го включвай в bug reports.",
      "Admin key дава право за отдалечена конфигурация.",
      "Направи защитен backup преди re-key или factory reset.",
    ],
  },
  network: {
    title: "Network: пази резервен път за управление",
    warning: true,
    text: "Грешен SSID, PSK или IP параметър може веднага да прекъсне TCP връзката.",
    bullets: ["При TCP промяна осигури BLE или USB fallback.", "Провери новия адрес преди масово прилагане."],
  },
  bluetooth: {
    title: "Bluetooth: текущата BLE сесия може да бъде прекъсната",
    warning: true,
    text: "Pairing mode, PIN и enabled флагът влияят директно на начина за повторно свързване.",
    bullets: ["Не изключвай BLE без TCP/USB fallback.", "Запиши новия fixed PIN в защитено място."],
  },
  power: {
    title: "Power: профилът зависи от ролята и захранването",
    warning: false,
    text: "Portable, sensor и infrastructure nodes имат различни нужди от sleep и wake поведение.",
    bullets: ["Router инфраструктурата изисква предвидимо захранване.", "Провери reachability след промяна на sleep timers."],
  },
  mqtt: {
    title: "MQTT: интернет bridge с ефект върху airtime и privacy",
    warning: false,
    text: "Uplink/downlink и channel настройките определят как интернет трафикът влиза в LoRa mesh-а.",
    bullets: ["Използвай custom channel PSK за частен трафик.", "Downlink към натоварен topic може да претовари локалната мрежа."],
  },
};

const configFieldHelp = {
  owner: {
    long_name: "Пълното име на възела, показвано в списъците и NodeInfo пакетите.",
    short_name: "Кратък идентификатор до 4 знака за тесни екрани и компактни изгледи.",
    is_licensed:
      "Маркира amateur-radio режим. Използвай само при валидно разрешително и спазвай местните изисквания, включително ограниченията за криптиране.",
    is_unmessagable:
      "Обявява, че възелът не приема лични съобщения. Полезно за инфраструктурни или еднопосочни nodes.",
  },
  device: {
    role: "Определя routing, power и broadcast поведението. CLIENT е безопасният избор за повечето устройства; използвай Role Advisor за сравнение.",
    button_gpio:
      "GPIO номер за потребителски бутон, когато платката няма предварително зададен такъв. Неправилен pin може да конфликтува с дисплей, GPS или LoRa хардуер.",
    buzzer_gpio:
      "GPIO номер за PWM buzzer, когато няма board default. Провери pinout-а и дали pin-ът поддържа необходимия изход.",
    rebroadcast_mode:
      "Филтрира кои пакети възелът препредава. LOCAL_ONLY ограничава до познатите канали; KNOWN_ONLY изисква и познат node в NodeDB.",
    node_info_broadcast_secs:
      "Секунди между периодичните NodeInfo пакети с име и идентичност. По-кратък интервал увеличава airtime; стандартно е рядко излъчване.",
    double_tap_as_button_press:
      "При поддържан accelerometer третира двойно почукване като натискане на потребителския бутон.",
    disable_triple_click:
      "Изключва стандартното тройно натискане на бутона за включване или изключване на GPS.",
    tzdef:
      "POSIX TZ string за локалното време на екрана и в логовете, например EET-2EEST,M3.5.0/3,M10.5.0/4 за България.",
    led_heartbeat_disabled:
      "Спира периодичното премигване на status LED. Не изключва непременно останалите индикации на платката.",
    buzzer_mode:
      "Определя кога firmware използва buzzer-а. Ефектът зависи от наличния хардуер и избрания buzzer GPIO.",
  },
  position: {
    position_broadcast_secs:
      "Базов интервал в секунди за изпращане на позиция. Кратките интервали използват повече airtime и батерия.",
    position_broadcast_smart_enabled:
      "Изпраща позиция според движение, изминато разстояние и minimum interval, вместо само по фиксиран таймер.",
    fixed_position:
      "Обявява последно зададената позиция като постоянна. Подходящо само за неподвижно и точно позиционирано устройство.",
    gps_update_interval:
      "Интервал за GPS опресняване. По-честото обновяване подобрява актуалността, но увеличава консумацията.",
    position_flags:
      "Bitmask кои допълнителни данни да влизат в position пакетите. Повече полета означават по-голям LoRa payload.",
    rx_gpio: "GPIO RX за външен GPS serial интерфейс. Провери pinout и voltage levels.",
    tx_gpio: "GPIO TX за външен GPS serial интерфейс. Провери pinout и voltage levels.",
    broadcast_smart_minimum_distance:
      "Минимално изминато разстояние преди smart position broadcast.",
    broadcast_smart_minimum_interval_secs:
      "Минимално време между smart position пакетите, независимо от движението.",
    gps_en_gpio:
      "GPIO за включване на захранването на външен GPS. Неправилен pin може да остави GPS изключен или постоянно включен.",
    gps_mode:
      "Режим на GPS приемника. Disabled спира GPS; Enabled управлява го нормално; Not present указва липсващ GPS хардуер.",
  },
  power: {
    is_power_saving:
      "Разрешава sleep режим и може да изключи BLE, Wi-Fi, serial, GPS и екрана. Осигури начин за събуждане или remote admin преди включване.",
    on_battery_shutdown_after_secs:
      "Изключва устройството след зададеното време без външно захранване. Използвай само ако board-ът отчита правилно external power.",
    adc_multiplier_override:
      "Калибрира изчисленото battery voltage. Грешна стойност води до неверен процент и power решения.",
    wait_bluetooth_secs:
      "Колко секунди устройството чака Bluetooth връзка преди sleep. По-голяма стойност улеснява свързването, но харчи повече батерия.",
    sds_secs: "Интервал за deep sleep. В sleep периодите устройството може да не е достижимо.",
    ls_secs: "Интервал за light sleep според power lifecycle-а на firmware.",
    min_wake_secs:
      "Минимално време, през което устройството остава будно след събуждане или активност.",
    device_battery_ina_address:
      "I²C адрес на INA2xx power monitor. Остави board default, ако не използваш конкретен външен сензор.",
    powermon_enables:
      "Bitmask за power-monitor каналите. Използвай само с позната схема на съответната платка.",
  },
  network: {
    wifi_enabled:
      "Включва Wi-Fi. Неправилни credentials могат да прекъснат TCP достъпа; запази BLE или USB fallback.",
    wifi_ssid: "Името на Wi-Fi мрежата. Стойността е чувствителна за operational privacy.",
    wifi_psk:
      "Wi-Fi паролата. MeshDesk не показва съществуващата стойност; празно поле я запазва.",
    ntp_server: "NTP hostname за сверяване на часовника при налична IP свързаност.",
    eth_enabled: "Включва Ethernet при поддържан хардуер.",
    address_mode:
      "Избира DHCP или статично адресиране според firmware възможностите. Осигури резервен transport преди промяна.",
    rsyslog_server:
      "Адрес на remote syslog сървър. Изпращането на diagnostics извън устройството има privacy и network ефект.",
    enabled_protocols:
      "Bitmask на разрешените IP услуги. Неправилна стойност може да спре очакван TCP/API достъп.",
    ipv6_enabled: "Разрешава IPv6 при поддържана мрежа и firmware.",
  },
  display: {
    screen_on_secs:
      "Колко секунди екранът остава включен след бутон или събитие. При firmware default стойност 0 обикновено означава 10 минути.",
    auto_screen_carousel_secs:
      "Автоматично преминава към следващата страница през зададения брой секунди. Стойност 0 изключва carousel-а.",
    flip_screen: "Завърта дисплея на 180° за обърнат монтаж.",
    units: "Избира metric или imperial единици за показваните стойности.",
    oled:
      "Драйвер за OLED controller. Остави auto-detect, освен ако дисплеят не се разпознава правилно.",
    displaymode:
      "Визуален режим на дисплея: стандартен, двуцветен, инвертиран или color според хардуера.",
    heading_bold: "Използва удебелено заглавие за по-добра четимост при inverted/two-color display.",
    wake_on_tap_or_motion:
      "Събужда екрана при движение, tap или capacitive touch, ако хардуерът го поддържа.",
    compass_orientation: "Компенсира физическата ориентация или обръщане на компаса на дисплея.",
    use_12h_clock: "Включва 12-часов формат; изключено използва 24-часов часовник.",
    use_long_node_name:
      "Показва long name вместо short name, когато екранът и firmware изгледът имат достатъчно място.",
    enable_message_bubbles:
      "Показва chat bubble оформление на поддържаните device дисплеи.",
  },
  lora: {
    use_preset:
      "Когато е включено, modem preset определя bandwidth, spreading factor и coding rate. Всички участници трябва да използват съвместими radio параметри.",
    modem_preset:
      "Готов баланс между обхват, скорост и airtime. LONG_FAST е разумна обща отправна точка.",
    bandwidth: "LoRa bandwidth за custom modem режим. Промяна може напълно да отдели възела от текущия mesh.",
    spread_factor:
      "LoRa spreading factor за custom режим. По-висок обикновено увеличава sensitivity и airtime.",
    coding_rate:
      "Forward-error-correction coding rate за custom режим. По-голяма защита добавя airtime overhead.",
    frequency_offset: "Фина честотна корекция за специализиран хардуер; обикновено остава 0.",
    region:
      "Регулаторен LoRa region според физическото местоположение. Изборът влияе на честоти, мощност и duty-cycle.",
    hop_limit:
      "Максимален брой mesh препредавания. По-висока стойност увеличава reach, но и airtime; 3 е добра начална стойност.",
    tx_enabled: "Разрешава LoRa предаване. Изключено превръща радиото в receive-only.",
    tx_power:
      "Предавателна мощност в dBm, ограничена от region и хардуера. Максимумът не винаги дава най-добра мрежа.",
    channel_num:
      "Frequency slot в избрания modem/region план. Несъвпадение отделя възела от останалите.",
    override_duty_cycle:
      "Заобикаля firmware duty-cycle защитата. Използвай само ако местната регулация изрично позволява това.",
    sx126x_rx_boosted_gain:
      "Включва boosted RX gain при SX126x. Може да подобри приемането с цената на по-висока консумация.",
    override_frequency:
      "Ръчно зададена честота. Advanced настройка с регулаторен риск и риск от загуба на свързаност.",
    pa_fan_disabled: "Изключва управлението на PA fan при хардуер, който го поддържа.",
    ignore_incoming: "Игнорира входящия LoRa трафик според firmware поведението.",
    ignore_mqtt: "Игнорира пакети, маркирани като дошли през MQTT.",
    config_ok_to_mqtt:
      "Разрешава избрани configuration данни да бъдат публикувани към MQTT. Прегледай privacy модела преди включване.",
  },
  bluetooth: {
    enabled:
      "Включва BLE. Не го изключвай, ако това е единственият ти резервен достъп до устройството.",
    mode:
      "Pairing режимът определя fixed PIN или случаен PIN от екрана. Random PIN изисква устройство с подходящ display.",
    fixed_pin:
      "Статичен Bluetooth PIN. Избери непредвидима стойност и не я публикувай в logs или screenshots.",
  },
  security: {
    public_key:
      "Public част на PKI идентичността. Полето е read-only в MeshDesk и може безопасно да се споделя само за trust/admin setup.",
    private_key:
      "Private PKI identity key. Никога не го споделяй; MeshDesk не го чете или експортира.",
    admin_key:
      "Public keys, които имат remote-admin права. Добавянето на ключ дава възможност за промяна и destructive команди.",
    is_managed:
      "Ограничава локалните промени и поставя устройството под managed policy. Активирай само с проверен recovery път.",
    serial_enabled: "Разрешава serial API/console според firmware и хардуера.",
    debug_log_api_enabled:
      "Разрешава debug logs през API. Полезно за диагностика, но увеличава обема и може да излага operational metadata.",
    admin_channel_enabled:
      "Разрешава legacy admin-channel управление. PKI admin е предпочитаният модел при поддържан firmware.",
  },
  mqtt: {
    enabled: "Включва MQTT module. Нужни са IP мрежа и коректен broker адрес.",
    address: "Hostname и по избор port на MQTT broker-а.",
    username: "MQTT потребител. Третирай го като чувствителна operational информация.",
    password: "MQTT парола. MeshDesk не показва текущата стойност; празно поле я запазва.",
    encryption_enabled: "Изпраща channel payload-а криптирано към MQTT, когато конфигурацията го поддържа.",
    json_enabled: "Публикува допълнителни JSON payload-и; увеличава broker traffic и излага decoded metadata.",
    tls_enabled: "Използва TLS до MQTT broker-а. Препоръчително за broker извън доверена локална мрежа.",
    root: "Root topic namespace за MQTT публикации и subscriptions.",
    proxy_to_client_enabled: "Проксира MQTT през свързан client вместо директната network връзка на радиото.",
    map_reporting_enabled:
      "Публикува map reports. Това може да разкрие приблизителна позиция и device metadata.",
  },
  store_forward: {
    enabled: "Включва Store & Forward module за възстановяване на пропуснати съобщения.",
    heartbeat: "Интервал за Store & Forward heartbeat/availability.",
    records: "Максимален брой съхранявани records според наличната памет.",
    history_return_max: "Максимален брой history записи в един отговор.",
    history_return_window: "Времеви прозорец за връщаната история.",
    is_server: "Прави възела Store & Forward server; най-подходящо за постоянно захранван инфраструктурен node.",
  },
  telemetry: {
    device_update_interval: "Интервал за device telemetry като батерия, voltage и channel utilization.",
    environment_update_interval: "Интервал за environment telemetry. По-кратките стойности увеличават airtime.",
    environment_measurement_enabled: "Включва четене и предаване от поддържани environment sensors.",
    environment_screen_enabled: "Показва environment telemetry на device екрана.",
    air_quality_enabled: "Включва поддържан air-quality sensor и съответната telemetry.",
    air_quality_interval: "Интервал между air-quality измерванията и предаванията.",
    power_measurement_enabled: "Включва telemetry от поддържан power monitor.",
    power_update_interval: "Интервал за power telemetry.",
    power_screen_enabled: "Показва power telemetry на device екрана.",
    health_measurement_enabled: "Включва поддържан health sensor.",
    health_update_interval: "Интервал за health telemetry.",
    health_screen_enabled: "Показва health telemetry на device екрана.",
    device_telemetry_enabled: "Разрешава периодичното изпращане на основната device telemetry.",
    air_quality_screen_enabled: "Показва air-quality telemetry на device екрана.",
  },
  neighbor_info: {
    enabled: "Включва Neighbor Info module за наблюдение на директно чуваните peers.",
    update_interval: "Интервал между Neighbor Info актуализациите; ниска стойност увеличава mesh airtime.",
    transmit_over_lora: "Предава Neighbor Info през LoRa. Изключи, ако данните са нужни само локално.",
  },
};

function configHelpFor(sectionName, field) {
  const explicit = configFieldHelp[sectionName]?.[field.name];
  if (explicit) return explicit;
  const path = `${sectionName}.${field.name}`;
  if (field.secret) {
    return `${path} е чувствителна стойност. MeshDesk не показва текущото съдържание; празно поле го оставя непроменено.`;
  }
  if (field.read_only) {
    return `${path} е read-only в MeshDesk, за да не бъде променено или разкрито опасно binary поле.`;
  }
  if (field.name.endsWith("_gpio") || field.name.endsWith("_pin")) {
    return `${path} избира физически GPIO pin. Провери pinout-а на точната платка, защото грешна стойност може да конфликтува с друг хардуер.`;
  }
  if (field.name.endsWith("_secs") || field.name.endsWith("_interval")) {
    return `${path} е времеви интервал, обикновено в секунди. По-малка стойност може да увеличи консумацията, packet rate или LoRa airtime.`;
  }
  if (field.name.endsWith("_enabled") || field.type === "bool") {
    return `${path} включва или изключва firmware поведение. Наличността и ефектът може да зависят от хардуера и firmware версията.`;
  }
  if (field.type === "enum") {
    return `${path} избира един от режимите, поддържани от текущия firmware. Запази recovery transport преди промяна на непознат режим.`;
  }
  return `${path} е Meshtastic firmware параметър. Променяй го само когато знаеш очакваната единица и допустимия диапазон за конкретния хардуер.`;
}

function helpTrigger(help, label) {
  return `<span class="help-trigger" tabindex="0" role="button"
    aria-label="${escapeHtml(label)}" data-help="${escapeHtml(help)}">i</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message || `HTTP ${response.status}`;
    const error = new Error(message);
    error.details = detail;
    error.status = response.status;
    throw error;
  }
  return data;
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = error ? "show error" : "show";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (element.className = ""), 4200);
}

function setTransport(transport) {
  state.transport = transport;
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.transport === transport);
  });
  $("#tcpFields").classList.toggle("hidden", transport !== "tcp");
  $("#bleFields").classList.toggle("hidden", transport !== "ble");
  $("#pairingBox").classList.toggle("hidden", transport !== "ble");
  $("#tcpDiscoveryResults").classList.toggle(
    "hidden",
    transport !== "tcp" || !state.discoveredTcpDevices.length,
  );
  $("#connectionDetail").textContent =
    transport === "tcp"
      ? "Нативен Meshtastic TCP порт 4403 — без HTTP/CORS."
      : "Bluetooth се обслужва от Linux BlueZ — без Web Bluetooth.";
}

async function discoverTcpDevices() {
  const button = $("#discoverTcpButton");
  button.disabled = true;
  button.textContent = "Откриване…";
  try {
    const result = await api("/api/discovery/tcp?timeout=3");
    state.discoveredTcpDevices = result.devices || [];
    const select = $("#tcpDiscoveredDevice");
    select.innerHTML = "";
    state.discoveredTcpDevices.forEach((device, index) => {
      const hostname = device.hostname ? ` · ${device.hostname}` : "";
      const identity = [device.short_name, device.node_id].filter(Boolean).join(" · ");
      select.add(
        new Option(
          `${device.name} · ${device.host}:${device.port}` +
            `${identity ? ` · ${identity}` : ""}${hostname}`,
          String(index),
        ),
      );
    });
    $("#tcpDiscoveryResults").classList.toggle(
      "hidden",
      !state.discoveredTcpDevices.length || state.transport !== "tcp",
    );
    if (state.discoveredTcpDevices.length) {
      renderTcpDiscoveryDetails();
      toast(`Открити TCP устройства: ${state.discoveredTcpDevices.length}`);
    } else {
      toast("Не е намерено Meshtastic TCP устройство чрез mDNS", true);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Открий";
  }
}

function matchingProfileForDiscoveredDevice(device) {
  const endpoints = new Set(
    [device.host, device.hostname, ...(device.addresses || [])]
      .filter(Boolean)
      .map((value) => String(value).toLocaleLowerCase()),
  );
  return (
    state.connectionProfiles.find(
      (profile) =>
        profile.transport === "tcp" &&
        ((profile.device_id &&
          device.node_id &&
          profile.device_id.toLocaleLowerCase() === device.node_id.toLocaleLowerCase()) ||
          (Number(profile.port) === Number(device.port) &&
            endpoints.has(String(profile.host).toLocaleLowerCase()))),
    ) || null
  );
}

function renderTcpDiscoveryDetails() {
  const container = $("#tcpDiscoveryDetails");
  const device = state.discoveredTcpDevices[Number($("#tcpDiscoveredDevice").value)];
  if (!device) {
    container.innerHTML = "";
    return;
  }
  const profile = matchingProfileForDiscoveredDevice(device);
  const txt = Object.entries(device.properties || {})
    .map(([key, value]) => `${key}=${value || "—"}`)
    .join(" · ");
  const discoveredName = device.short_name
    ? `${device.name} · ${device.short_name}`
    : device.name;
  const nodeId = profile?.device_id || device.node_id;
  container.innerHTML = `
    <div class="tcp-discovery-identity">
      <div>
        <span>${profile?.device_id ? "ПОТВЪРДЕН ПРОФИЛ" : "mDNS ИДЕНТИЧНОСТ"}</span>
        <strong>${escapeHtml(
          profile?.device_name || profile?.name || discoveredName,
        )}</strong>
      </div>
      ${
        nodeId
          ? `<code>${escapeHtml(nodeId)}</code>`
          : "<em>Името на радиото ще се потвърди след свързване</em>"
      }
    </div>
    <dl>
      <div><dt>IP адрес</dt><dd>${escapeHtml((device.addresses || []).join(", ") || device.host)}</dd></div>
      <div><dt>Hostname</dt><dd>${escapeHtml(device.hostname || "не е публикуван")}</dd></div>
      <div><dt>TCP порт</dt><dd>${escapeHtml(device.port)}</dd></div>
      <div><dt>MAC / neighbor</dt><dd>${escapeHtml(
        device.mac || "не е наличен",
      )}</dd></div>
      <div><dt>Node ID</dt><dd>${escapeHtml(device.node_id || "не е публикуван")}</dd></div>
      <div><dt>Short name</dt><dd>${escapeHtml(device.short_name || "не е публикуван")}</dd></div>
      <div><dt>Platform</dt><dd>${escapeHtml(device.platform || "не е публикувана")}</dd></div>
      <div><dt>mDNS service</dt><dd>${escapeHtml(device.name)}</dd></div>
      <div><dt>TXT metadata</dt><dd>${escapeHtml(txt || "няма публикувани TXT полета")}</dd></div>
    </dl>`;
}

function useDiscoveredTcpDevice() {
  const index = Number($("#tcpDiscoveredDevice").value);
  const device = state.discoveredTcpDevices[index];
  if (!device) return;
  $("#tcpHost").value = device.host;
  $("#tcpPort").value = device.port;
  markConnectionProfileDirty();
  toast(`Избран endpoint: ${device.host}:${device.port}`);
}

function connectionValues() {
  return state.transport === "tcp"
    ? {
        transport: "tcp",
        host: $("#tcpHost").value.trim(),
        port: Number($("#tcpPort").value),
        address: "",
      }
    : {
        transport: "ble",
        host: "",
        port: 4403,
        address: $("#bleDevice").value,
      };
}

function connectionTarget(values) {
  return values.transport === "tcp"
    ? `${values.host || "—"}:${values.port || 4403}`
    : values.address || "Няма избрано BLE устройство";
}

function selectedConnectionProfile() {
  const profileId = $("#connectionProfile").value;
  return state.connectionProfiles.find((profile) => profile.id === profileId) || null;
}

function updateConnectionProfileUi() {
  const profile = selectedConnectionProfile();
  const identity = $("#connectionIdentityStatus");
  const rebind = $("#rebindConnectionProfile");
  $("#saveConnectionProfile").textContent = profile ? "Обнови профила" : "Запази като профил";
  $("#deleteConnectionProfile").classList.toggle("hidden", !profile);
  if (!profile) {
    $("#connectionProfileHint").textContent =
      "Профилите пазят само адреса и транспорта локално — без PIN, PSK или ключове.";
    identity.className = "connection-identity-status hidden";
    rebind.classList.add("hidden");
    return;
  }
  const modified = state.connectionProfileDirty ? " · има незаписани промени" : "";
  const lastUsed = profile.last_used_at
    ? new Date(profile.last_used_at).toLocaleString()
    : "никога";
  $("#connectionProfileHint").textContent =
    `${connectionTarget(profile)}${modified}. Последно използван: ${lastUsed}`;
  if (state.connectionIdentityMismatch) {
    const mismatch = state.connectionIdentityMismatch;
    identity.className = "connection-identity-status mismatch";
    $("#connectionIdentityTitle").textContent = "Свързано е различно радио";
    $("#connectionIdentityDetail").textContent =
      `Очаквано: ${mismatch.expected_name || mismatch.expected_id} · ` +
      `открито: ${mismatch.observed_name || mismatch.observed_id}.`;
    rebind.classList.remove("hidden");
  } else if (profile.device_id) {
    identity.className = `connection-identity-status verified${
      state.connectionProfileDirty ? " modified" : ""
    }`;
    $("#connectionIdentityTitle").textContent = state.connectionProfileDirty
      ? "Запазената идентичност е за стария endpoint"
      : "Потвърдено Meshtastic устройство";
    $("#connectionIdentityDetail").textContent =
      `${profile.device_name || profile.device_id} · ${profile.device_id}` +
      (profile.identity_last_verified_at
        ? ` · проверено ${new Date(profile.identity_last_verified_at).toLocaleString()}`
        : "");
    rebind.classList.add("hidden");
  } else {
    identity.className = "connection-identity-status pending";
    $("#connectionIdentityTitle").textContent = "Идентичността още не е потвърдена";
    $("#connectionIdentityDetail").textContent =
      "Ще бъде записана автоматично след успешния Meshtastic handshake.";
    rebind.classList.add("hidden");
  }
}

function renderConnectionProfiles(selectedId = "") {
  const select = $("#connectionProfile");
  const activeId = selectedId || select.value;
  select.innerHTML = "";
  select.add(new Option("Ръчно въвеждане", ""));
  state.connectionProfiles.forEach((profile) => {
    const transport = profile.transport === "tcp" ? "TCP" : "BLE";
    select.add(new Option(`${profile.name} · ${transport}`, profile.id));
  });
  select.value = state.connectionProfiles.some((profile) => profile.id === activeId)
    ? activeId
    : "";
  updateConnectionProfileUi();
  if (state.discoveredTcpDevices.length) renderTcpDiscoveryDetails();
}

function applyConnectionProfile() {
  const profile = selectedConnectionProfile();
  state.connectionProfileDirty = false;
  state.connectionIdentityMismatch = null;
  if (!profile) {
    updateConnectionProfileUi();
    return;
  }
  setTransport(profile.transport);
  if (profile.transport === "tcp") {
    $("#tcpHost").value = profile.host;
    $("#tcpPort").value = profile.port;
  } else {
    const select = $("#bleDevice");
    if (![...select.options].some((option) => option.value === profile.address)) {
      select.add(new Option(`${profile.name} — ${profile.address}`, profile.address));
    }
    select.value = profile.address;
  }
  updateConnectionProfileUi();
}

function markConnectionProfileDirty() {
  if (!selectedConnectionProfile()) return;
  state.connectionProfileDirty = true;
  state.connectionIdentityMismatch = null;
  updateConnectionProfileUi();
}

async function refreshConnectionProfiles(selectedId = "") {
  try {
    const result = await api("/api/connection-profiles");
    state.connectionProfiles = result.profiles || [];
    renderConnectionProfiles(selectedId);
  } catch (error) {
    toast(`Профилите не могат да бъдат заредени: ${error.message}`, true);
  }
}

function openConnectionProfileModal() {
  const profile = selectedConnectionProfile();
  const values = connectionValues();
  state.connectionProfileModalId = profile?.id || null;
  $("#connectionProfileModalTitle").textContent = profile
    ? "Обнови профила"
    : "Запази връзката";
  $("#connectionProfileSummary").textContent =
    `${values.transport.toUpperCase()} · ${connectionTarget(values)}. ` +
    "PIN, channel PSK и ключове не се съхраняват.";
  $("#connectionProfileName").value =
    profile?.name ||
    (values.transport === "tcp"
      ? values.host
      : $("#bleDevice").selectedOptions[0]?.text || "");
  $("#connectionProfileModal").classList.remove("hidden");
  setTimeout(() => $("#connectionProfileName").focus(), 50);
}

function closeConnectionProfileModal() {
  $("#connectionProfileModal").classList.add("hidden");
  state.connectionProfileModalId = null;
  $("#saveConnectionProfile").focus();
}

async function saveConnectionProfile() {
  const name = $("#connectionProfileName").value.trim();
  if (!name) {
    toast("Въведи име на профила", true);
    $("#connectionProfileName").focus();
    return;
  }
  const profileId = state.connectionProfileModalId;
  try {
    const result = await api(
      profileId
        ? `/api/connection-profiles/${encodeURIComponent(profileId)}`
        : "/api/connection-profiles",
      {
        method: profileId ? "PUT" : "POST",
        body: JSON.stringify({ name, ...connectionValues() }),
      },
    );
    $("#connectionProfileModal").classList.add("hidden");
    state.connectionProfileModalId = null;
    state.connectionProfileDirty = false;
    await refreshConnectionProfiles(result.profile.id);
    applyConnectionProfile();
    toast(profileId ? "Профилът е обновен" : "Връзката е запазена като профил");
  } catch (error) {
    toast(error.message, true);
  }
}

async function deleteConnectionProfile() {
  const profile = selectedConnectionProfile();
  if (!profile || !confirm(`Да изтрия ли профила „${profile.name}“?`)) return;
  try {
    await api(`/api/connection-profiles/${encodeURIComponent(profile.id)}`, {
      method: "DELETE",
    });
    state.connectionProfileDirty = false;
    state.connectionIdentityMismatch = null;
    await refreshConnectionProfiles();
    toast("Профилът е изтрит");
  } catch (error) {
    toast(error.message, true);
  }
}

async function verifySelectedConnectionProfile(status, allowRebind = false) {
  const profile = selectedConnectionProfile();
  if (
    !profile ||
    state.connectionProfileDirty ||
    status?.state !== "connected" ||
    !status.profile_id
  ) {
    return;
  }
  try {
    const result = await api(
      `/api/connection-profiles/${encodeURIComponent(profile.id)}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ allow_rebind: allowRebind }),
      },
    );
    state.connectionProfiles = state.connectionProfiles.map((item) =>
      item.id === result.profile.id ? result.profile : item,
    );
    state.connectionIdentityMismatch = null;
    renderConnectionProfiles(result.profile.id);
    if (allowRebind) toast("Профилът е свързан с новото радио");
  } catch (error) {
    if (error.details?.code === "identity_mismatch") {
      state.connectionIdentityMismatch = error.details;
      updateConnectionProfileUi();
      toast("Профилът очаква друго Meshtastic устройство", true);
      return;
    }
    toast(`Идентичността не може да бъде проверена: ${error.message}`, true);
  }
}

async function rebindConnectionProfile() {
  const mismatch = state.connectionIdentityMismatch;
  if (!mismatch || !state.status) return;
  const observed = mismatch.observed_name || mismatch.observed_id;
  if (
    !confirm(
      `Профилът ще бъде свързан с „${observed}“. ` +
        "Направи това само ако устройството е сменено умишлено. Да продължа ли?",
    )
  ) {
    return;
  }
  await verifySelectedConnectionProfile(state.status, true);
}

function updateControls(status) {
  state.status = status;
  state.connection = status.state;
  const connected = status.state === "connected";
  const busy = status.state === "connecting";
  const pill = $("#statusPill");
  pill.className = `status ${status.state}`;
  pill.querySelector("strong").textContent = statusLabels[status.state] || status.state;

  const showCompact = connected || busy;
  $("#connectionCompact").classList.toggle("hidden", !showCompact);
  $("#connectionDetails").classList.toggle(
    "hidden",
    showCompact && !state.connectionExpanded,
  );
  $("#connectionPanel").classList.toggle(
    "compact",
    showCompact && !state.connectionExpanded,
  );
  $("#connectionToggle").textContent = state.connectionExpanded ? "Скрий" : "Настройки";
  const user = status.my_node?.user || {};
  $("#connectedDeviceName").textContent =
    user.longName || user.long_name || status.target || "Meshtastic радио";
  $("#connectedTransport").textContent = (status.transport || state.transport).toUpperCase();
  $("#connectedTarget").textContent =
    busy ? `Свързване към ${status.target || "устройството"}…` : status.target || "—";

  $("#connectButton").disabled = busy || connected;
  $("#connectButton").textContent = busy ? "Свързване…" : "Свържи";
  $("#disconnectButton").disabled = !busy && !connected;
  $("#messageText").disabled = !connected;
  $("#channel").disabled = !connected;
  $("#wantAck").disabled = !connected;
  $("#sendButton").disabled = !connected;
  $("#newDirectButton").disabled = !connected;
  $("#refreshNodes").disabled = !connected;
  $("#reloadChannels").disabled = !connected;
  $("#reloadConfig").disabled = !connected;
  $("#configTarget").disabled = !connected;
  $("#exportConfig").disabled = !connected;
  $("#importConfig").disabled = !connected;
  $("#syncHistory").disabled = !connected;
  $("#adminTarget").disabled = !connected;
  document.querySelectorAll(".admin-action").forEach((button) => {
    button.disabled = !connected;
  });
  $("#localPublicKey").textContent = status.public_key || "—";
  updateConnectionHealth(status);
  applyRequestCooldowns();
  updateChatQueueIndicator();
  updateByteCount();
  if (status.error && status.error !== state.lastError) toast(status.error, true);
  state.lastError = status.error;
}

function updateChatQueueIndicator() {
  const subtitle = $("#chatSubtitle");
  if (!subtitle) return;
  const meta = conversationMeta(state.selectedConversation);
  const queue = state.status?.tx_queue;
  const applicationCount =
    Number(queue?.application_pending || 0) + (queue?.active_client_id ? 1 : 0);
  const radio = queue?.radio || {};
  const radioFull = radio.free === 0 && radio.max_length != null;
  const details = [];
  if (applicationCount) details.push(`TX: ${applicationCount} чака`);
  if (radioFull) details.push(`radio queue: 0/${radio.max_length} свободни`);
  subtitle.textContent = [meta.subtitle, ...details].filter(Boolean).join(" · ");
}

function activeRequestCooldown(action, nodeId) {
  const active = state.status?.request_controls?.active || [];
  const now = Date.now();
  return active.find(
    (item) =>
      item.action === action &&
      item.expires_at_ms > now &&
      (item.scope === "global" || item.target?.toLowerCase() === nodeId?.toLowerCase()),
  );
}

function applyRequestCooldowns() {
  document.querySelectorAll("[data-request-action]").forEach((button) => {
    const cooldown = activeRequestCooldown(
      button.dataset.requestAction,
      button.dataset.node,
    );
    const label = button.dataset.defaultLabel || button.textContent.trim();
    button.dataset.defaultLabel = label.replace(/\s+\(\d+s\)$/, "");
    if (cooldown) {
      const seconds = Math.max(1, Math.ceil((cooldown.expires_at_ms - Date.now()) / 1000));
      button.disabled = true;
      button.textContent = `${button.dataset.defaultLabel} (${seconds}s)`;
      button.title =
        cooldown.scope === "global"
          ? `Общ Meshtastic cooldown: още ${seconds} секунди`
          : `Cooldown за този възел: още ${seconds} секунди`;
    } else {
      button.disabled = state.connection !== "connected";
      button.textContent = button.dataset.defaultLabel;
      button.removeAttribute("title");
    }
  });
}

function updateConnectionHealth(status) {
  const health = status.health || {
    state:
      status.state === "connected"
        ? "healthy"
        : status.state === "connecting"
          ? "connecting"
          : status.state === "error"
            ? "failed"
            : "idle",
    connected_at: status.connected_at,
    detail: status.error,
    transport: status.transport,
    target: status.target,
  };
  const panel = $("#connectionHealthPanel");
  const visible = health.state !== "idle" || Boolean(health.target);
  panel.className = `connection-health-panel ${health.state}${
    visible ? "" : " hidden"
  }`;
  $("#connectionHealthDot").className = `connection-health-dot ${health.state}`;
  $("#connectionHealthTitle").textContent =
    healthLabels[health.state] || health.state;
  const reason =
    disconnectReasonLabels[health.reason] ||
    health.detail ||
    (health.state === "healthy"
      ? `Активна от ${elapsedTime(health.connected_at)}`
      : "");
  $("#connectionHealthReason").textContent = reason;
  $("#healthTarget").textContent = [health.transport?.toUpperCase(), health.target]
    .filter(Boolean)
    .join(" · ") || "—";
  $("#healthConnectedAt").textContent = relativeTime(
    health.connected_at || health.connect_started_at,
  );
  $("#healthLastActivity").textContent = relativeTime(health.last_activity_at);
  $("#healthLastRx").textContent = relativeTime(health.last_rx_at);
  $("#healthDisconnectedAt").textContent = relativeTime(health.disconnected_at);
  $("#healthReconnectPolicy").textContent = health.reconnect_eligible
    ? "Допустим след изрично включване"
    : "Не е допустим за това състояние";
  $("#connectionHealthCompact").textContent =
    health.state === "healthy"
      ? `активна ${elapsedTime(health.connected_at)}`
      : health.state === "connecting"
        ? "handshake…"
        : healthLabels[health.state] || health.state;
}

async function refreshStatus() {
  try {
    const status = await api("/api/status");
    const profileChanged = (status.profile_id || null) !== state.profileId;
    if (profileChanged) {
      await activateProfile(status.profile_id || null, status.event_sequence);
    }
    if (state.readThrough > status.event_sequence) {
      state.readThrough = 0;
      state.unread = {};
      localStorage.removeItem("meshdeskReadThrough");
    }
    const wasConnected = state.connection === "connected";
    if (!wasConnected && status.state === "connected") {
      state.connectionExpanded = false;
    } else if (status.state !== "connected" && status.state !== "connecting") {
      state.connectionExpanded = true;
    }
    if (
      wasConnected &&
      status.state !== "connected" &&
      status.state !== "connecting"
    ) {
      clearDeviceBoundUi(
        disconnectReasonLabels[status.health?.reason] || "Disconnected",
        status.event_sequence,
      );
    }
    updateControls(status);
    if (!wasConnected && status.state === "connected") {
      toast(`Свързано: ${status.target}`);
      await verifySelectedConnectionProfile(status);
      if (state.sessionUiCleared && !profileChanged) {
        await activateProfile(status.profile_id || null, status.event_sequence);
      }
      state.sessionUiCleared = false;
      await Promise.all([
        refreshNodes(),
        refreshChannels(),
        refreshChannelSlots(),
        refreshConfig(),
      ]);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

function clearDeviceBoundUi(reason = "Disconnected", eventSequence = state.lastEvent) {
  state.chatMessages = {};
  state.deliveryReceipts = {};
  state.eventLog = [];
  state.unread = {};
  state.selectedConversation = null;
  state.closedConversations.clear();
  state.nodes = [];
  state.channels = [];
  state.channelSlots = [];
  state.activeChannelSlot = null;
  state.configSections = [];
  state.activeConfig = null;
  state.lastEvent = Math.max(state.lastEvent, eventSequence || 0);
  state.sessionUiCleared = true;
  if (state.inspector) closeInspector();
  $("#configTarget").value = "";
  $("#adminTarget").value = "";
  $("#remoteConfigControls").classList.add("hidden");
  $("#configPanel").open = false;
  $("#adminPanel").open = false;
  selectSettingsView("config");
  renderNodes([]);
  renderChannels([]);
  renderChannelSlots([]);
  renderConfig([]);
  renderUnread();
  $("#events").className = "events empty-state";
  $("#events").textContent = reason;
}

async function activateProfile(profileId, eventSequence) {
  state.profileId = profileId;
  state.lastEvent = eventSequence || 0;
  state.chatMessages = {};
  state.deliveryReceipts = {};
  state.eventLog = [];
  state.unread = {};
  state.selectedConversation = null;
  state.closedConversations.clear();
  state.nodes = [];
  state.channels = [];
  state.channelSlots = [];
  state.activeChannelSlot = null;
  state.readThrough = 0;
  $("#events").className = "events empty-state";
  $("#events").textContent = "Все още няма събития.";
  renderNodes([]);
  renderChannels([]);
  renderChannelSlots([]);
  renderConfig([]);
  renderUnread();
  if (!profileId) return;
  try {
    const { events } = await api("/api/history");
    appendEvents(events, { historical: true });
  } catch (error) {
    toast(`Историята не може да бъде заредена: ${error.message}`, true);
  }
}

async function connect(event) {
  event.preventDefault();
  const profile = selectedConnectionProfile();
  const body = {
    ...connectionValues(),
    connection_profile_id:
      profile && !state.connectionProfileDirty ? profile.id : null,
  };
  try {
    const status = await api("/api/connect", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (body.connection_profile_id) await refreshConnectionProfiles(profile.id);
    updateControls(status);
  } catch (error) {
    toast(error.message, true);
  }
}

async function disconnect() {
  try {
    state.connectionExpanded = true;
    const status = await api("/api/disconnect", { method: "POST" });
    clearDeviceBoundUi("Disconnected · прекъснато от оператора", status.event_sequence);
    updateControls(status);
  } catch (error) {
    toast(error.message, true);
  }
}

async function scanBle() {
  const button = $("#scanButton");
  button.disabled = true;
  button.textContent = "Сканиране…";
  try {
    const { devices } = await api("/api/ble/scan");
    const select = $("#bleDevice");
    select.innerHTML = "";
    if (!devices.length) {
      select.add(new Option("Не е намерено Meshtastic устройство", ""));
      toast("Не е намерено Meshtastic BLE устройство", true);
    } else {
      devices.forEach((device) =>
        select.add(new Option(`${device.name} — ${device.address}`, device.address)),
      );
      toast(`Намерени устройства: ${devices.length}`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Сканирай";
  }
}

async function startPairing() {
  const address = $("#bleDevice").value;
  if (!address) {
    toast("Първо избери Bluetooth устройство", true);
    return;
  }
  if (
    $("#forgetExisting").checked &&
    !confirm("Старото BlueZ сдвояване ще бъде изтрито. Да продължа ли?")
  ) {
    return;
  }
  try {
    await api("/api/ble/pair", {
      method: "POST",
      body: JSON.stringify({
        address,
        forget_existing: $("#forgetExisting").checked,
      }),
    });
    $("#pairingPin").value = "";
    $("#pairingModal").classList.remove("hidden");
    $("#pairingModalStatus").textContent =
      "Изчакай PIN на екрана на радиото, въведи го тук и потвърди.";
    $("#submitPin").disabled = false;
    setTimeout(() => $("#pairingPin").focus(), 50);
    $("#pairButton").disabled = true;
    $("#pairingTitle").textContent = "Сдвояване в ход…";
    $("#pairingStatus").textContent =
      "Събуди радиото и изчакай да се появи PIN на неговия екран.";
  } catch (error) {
    toast(error.message, true);
  }
}

async function submitPairingPin() {
  try {
    await api("/api/ble/pair/pin", {
      method: "POST",
      body: JSON.stringify({ pin: $("#pairingPin").value.trim() }),
    });
    $("#submitPin").disabled = true;
    $("#pairingModalStatus").textContent = "BlueZ проверява PIN кода…";
  } catch (error) {
    toast(error.message, true);
  }
}

async function cancelPairing() {
  try {
    await api("/api/ble/pair", { method: "DELETE" });
  } catch {
    // Closing the dialog is still useful if the backend is restarting.
  }
  $("#pairingModal").classList.add("hidden");
  $("#pairButton").disabled = false;
}

async function pollPairing() {
  if (state.transport !== "ble") return;
  try {
    const pairing = await api("/api/ble/pair");
    const activeStates = ["starting", "pairing", "waiting_for_pin", "pin_received"];
    const active = activeStates.includes(pairing.state);
    $("#pairButton").disabled = active;
    const messages = {
      idle: "Стартирай сдвояване и изчакай PIN на екрана на радиото.",
      starting: "Стартира BlueZ pairing agent…",
      pairing: "Изчаква се радиото да поиска PIN…",
      waiting_for_pin: "Въведи PIN кода, който се вижда на радиото.",
      pin_received: "PIN кодът е приет. Изчаква се BlueZ потвърждение…",
      paired: "Сдвояването е успешно. Вече можеш да натиснеш „Свържи“.",
      cancelled: "Сдвояването е отказано.",
    };
    $("#pairingStatus").textContent =
      pairing.error || messages[pairing.state] || pairing.state;
    $("#pairingTitle").textContent =
      pairing.state === "paired" ? "Успешно сдвоено" : "Bluetooth сдвояване";
    if (pairing.state === "waiting_for_pin") {
      $("#pairingModal").classList.remove("hidden");
      $("#pairingModalStatus").textContent =
        "Радиото чака PIN. Въведи показания код и натисни „Потвърди PIN“.";
      $("#submitPin").disabled = false;
    } else if (pairing.state === "pin_received") {
      $("#pairingModalStatus").textContent = "PIN кодът е подаден към BlueZ…";
      $("#submitPin").disabled = true;
    }
    if (pairing.state === "paired" && pollPairing.previous !== "paired") {
      $("#pairingModal").classList.add("hidden");
      toast("Bluetooth сдвояването е успешно");
    }
    if (pairing.state === "error" && pollPairing.previous !== "error") {
      $("#pairingModalStatus").textContent =
        pairing.error || "Неуспешно Bluetooth сдвояване";
      $("#submitPin").disabled = false;
      toast(pairing.error || "Неуспешно Bluetooth сдвояване", true);
    }
    pollPairing.previous = pairing.state;
  } catch {
    // Status polling will recover.
  }
}

function formatAge(timestamp) {
  if (!timestamp) return "неизвестно";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
  if (seconds < 60) return `преди ${seconds}s`;
  if (seconds < 3600) return `преди ${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `преди ${Math.floor(seconds / 3600)}h`;
  return `преди ${Math.floor(seconds / 86400)}d`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function nodeForId(nodeId) {
  const normalized = String(nodeId || "").toLowerCase();
  return state.nodes.find((node) => node.id.toLowerCase() === normalized);
}

function conversationMeta(key) {
  if (!key) {
    return {
      title: "Избери разговор",
      subtitle: "Свържи радио, за да четеш и изпращаш съобщения.",
      avatar: "·",
      type: "none",
    };
  }
  if (key.startsWith("direct:")) {
    const nodeId = key.slice("direct:".length);
    const node = nodeForId(nodeId);
    return {
      title: node?.long_name || nodeId,
      subtitle: node
        ? `${node.short_name} · ${node.id} · личен разговор`
        : `${nodeId} · личен разговор`,
      avatar: (node?.short_name || nodeId.slice(-4)).slice(0, 4),
      type: "direct",
      destination: nodeId,
    };
  }
  const index = Number(key.slice("channel:".length));
  const channel = state.channels.find((item) => item.index === index);
  return {
    title: `# ${channel?.name || (index === 0 ? "Primary" : `Channel ${index}`)}`,
    subtitle: `Канал ${index}${channel?.encrypted ? " · криптиран" : ""}${
      channel?.role ? ` · ${channel.role}` : ""
    }`,
    avatar: "#",
    type: "channel",
    channel: index,
  };
}

function conversationKeys() {
  const channelKeys = state.channels.length
    ? state.channels.map((channel) => `channel:${channel.index}`)
    : state.connection === "connected"
      ? ["channel:0"]
      : [];
  const dynamicKeys = Object.keys(state.chatMessages);
  return [...new Set([...channelKeys, ...dynamicKeys])]
    .filter((key) => !state.closedConversations.has(key))
    .sort((left, right) => {
      const leftChannel = left.startsWith("channel:");
      const rightChannel = right.startsWith("channel:");
      if (leftChannel !== rightChannel) return leftChannel ? -1 : 1;
      if (leftChannel) {
        return Number(left.slice(8)) - Number(right.slice(8));
      }
      const leftTime = state.chatMessages[left]?.at(-1)?.time || "";
      const rightTime = state.chatMessages[right]?.at(-1)?.time || "";
      return rightTime.localeCompare(leftTime);
    });
}

function messageTime(value) {
  if (!value) return "";
  const timestamp = new Date(value);
  const olderThanDay = Date.now() - timestamp.getTime() >= 24 * 60 * 60 * 1000;
  return olderThanDay
    ? timestamp.toLocaleString([], {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderConversations() {
  const container = $("#conversationList");
  const query = $("#conversationSearch").value.trim().toLocaleLowerCase("bg");
  const keys = conversationKeys().filter((key) => {
    const meta = conversationMeta(key);
    return !query || `${meta.title} ${meta.subtitle}`.toLocaleLowerCase("bg").includes(query);
  });
  if (!keys.length) {
    container.className = "conversation-list empty-state";
    container.textContent =
      state.connection === "connected"
        ? "Няма разговор, който отговаря на търсенето."
        : "Каналите ще се покажат след свързване.";
    return;
  }
  container.className = "conversation-list";
  container.innerHTML = keys
    .map((key) => {
      const meta = conversationMeta(key);
      const last = state.chatMessages[key]?.at(-1);
      const preview = last?.text || (meta.type === "channel" ? "Meshtastic канал" : "Нов разговор");
      const unread = state.unread[key] || 0;
      return `
        <button type="button" class="conversation-item ${
          key === state.selectedConversation ? "active" : ""
        }" data-conversation="${escapeHtml(key)}">
          <span class="conversation-avatar">${escapeHtml(meta.avatar)}</span>
          <span class="conversation-copy">
            <strong>${escapeHtml(meta.title)}</strong>
            <span>${escapeHtml(preview)}</span>
          </span>
          <span class="conversation-meta">
            <time>${escapeHtml(messageTime(last?.time))}</time>
            ${unread ? `<b class="conversation-unread">${unread}</b>` : ""}
          </span>
        </button>`;
    })
    .join("");
  container.querySelectorAll(".conversation-item").forEach((button) => {
    button.addEventListener("click", () => selectConversation(button.dataset.conversation));
  });
}

function deliveryLabel(message) {
  if (message.delivery === "queued")
    return '<span class="delivery queued">⌛ в радио опашката</span>';
  if (message.delivery === "sent")
    return '<span class="delivery sent">↑ предадено на радиото</span>';
  if (message.delivery === "delivered") return '<span class="delivery delivered">✓ ACK</span>';
  if (message.delivery === "failed") return '<span class="delivery failed">× NAK</span>';
  if (message.delivery === "timeout")
    return '<span class="delivery failed">⌛ без ACK / timeout</span>';
  if (message.wantAck)
    return '<span class="delivery pending">… предадено · чака ACK</span>';
  return "";
}

function renderChat() {
  if (!state.selectedConversation && conversationKeys().length) {
    state.selectedConversation = conversationKeys()[0];
  }
  const key = state.selectedConversation;
  const meta = conversationMeta(key);
  $("#chatAvatar").textContent = meta.avatar;
  $("#chatTitle").textContent = meta.title;
  updateChatQueueIndicator();

  const messages = key ? state.chatMessages[key] || [] : [];
  const container = $("#chatMessages");
  const wasNearBottom =
    container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  if (!messages.length) {
    container.className = "chat-messages empty-state";
    container.textContent = key
      ? "Няма съобщения в този разговор. Напиши първото."
      : "Тук ще се появи историята на избрания канал или личен разговор.";
  } else {
    container.className = "chat-messages";
    container.innerHTML = messages
      .map((message) => {
        const sender = message.direction === "outgoing"
          ? "Аз"
          : conversationMeta(`direct:${message.from || "unknown"}`).title;
        const avatar = message.direction === "outgoing"
          ? "ME"
          : (nodeForId(message.from || "")?.short_name || "RX").slice(0, 4);
        return `
          <article class="message-row ${message.direction}">
            <span class="message-sender-avatar">${escapeHtml(avatar)}</span>
            <div class="message-stack">
              <div class="message-sender">${escapeHtml(sender)}</div>
              <div class="message-bubble">${escapeHtml(message.text)}</div>
              <div class="message-footer">
                <button type="button" class="reply-message" data-conversation="${escapeHtml(
                  key,
                )}">Отговори</button>
                <button type="button" class="message-info" data-event-id="${escapeHtml(
                  message.eventId,
                )}" title="Покажи packet metadata">ⓘ Детайли</button>
                <time>${escapeHtml(messageTime(message.time))}</time>
                ${
                  message.sourceEvent?.recovered
                    ? '<span class="delivery recovered">↻ от радиото</span>'
                    : ""
                }
                ${message.direction === "outgoing" ? deliveryLabel(message) : ""}
              </div>
            </div>
          </article>`;
      })
      .join("");
    container.querySelectorAll(".reply-message").forEach((button) => {
      button.addEventListener("click", () => {
        selectConversation(button.dataset.conversation);
        $("#messageText").focus();
      });
    });
    container.querySelectorAll(".message-info").forEach((button) => {
      button.addEventListener("click", () =>
        openMessageInspector(button.dataset.eventId),
      );
    });
    if (wasNearBottom) container.scrollTop = container.scrollHeight;
  }

  if (key?.startsWith("channel:")) {
    $("#channel").value = key.slice("channel:".length);
  }
  const connected = state.connection === "connected";
  $("#channel").disabled = !connected;
  $("#messageText").disabled = !connected || !key;
  $("#messageText").placeholder = key
    ? `Съобщение до ${meta.title}…`
    : "Избери разговор…";
  $("#markConversationRead").disabled = !key || !(state.unread[key] > 0);
  $("#closeConversation").disabled = !key || meta.type === "channel";
  $("#closeConversation").title =
    meta.type === "channel"
      ? "Конфигурираните канали се управляват от Channel Manager"
      : "Скрий разговора, без да изтриваш историята";
  updateByteCount();
}

function selectConversation(key) {
  state.closedConversations.delete(key);
  state.selectedConversation = key;
  state.unread[key] = 0;
  renderConversations();
  renderChat();
}

function closeConversation() {
  const key = state.selectedConversation;
  if (!key || key.startsWith("channel:")) return;
  state.closedConversations.add(key);
  state.selectedConversation = null;
  renderConversations();
  renderChat();
}

function fillDirectRecipients() {
  const select = $("#directRecipient");
  const current = select.value;
  select.innerHTML = '<option value="__manual">Въведи node ID…</option>';
  state.nodes.forEach((node) => {
    const option = new Option(
      `${node.long_name} (${node.short_name}) · ${node.id}${
        node.is_messageable ? "" : " · не приема DM"
      }`,
      node.id,
    );
    option.disabled = !node.is_messageable;
    select.add(option);
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
  $("#directManualLabel").classList.toggle("hidden", select.value !== "__manual");
}

function fillConfigTargets() {
  const select = $("#configTarget");
  const current = select.value;
  select.innerHTML = `<option value="">Локално: ${escapeHtml(
    state.status?.profile_name || state.profileId || "радио",
  )}</option>`;
  state.nodes.forEach((node) => {
    select.add(
      new Option(
        `Remote: ${node.long_name} (${node.short_name}) · ${node.id}`,
        node.id,
      ),
    );
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
  $("#remoteConfigControls").classList.toggle("hidden", !select.value);
  fillAdminTargets();
}

function fillAdminTargets() {
  const select = $("#adminTarget");
  const current = select.value;
  select.innerHTML = `<option value="">Локално: ${escapeHtml(
    state.status?.profile_name || state.profileId || "радио",
  )}</option>`;
  state.nodes.forEach((node) => {
    select.add(
      new Option(
        `Remote: ${node.long_name} (${node.short_name}) · ${node.id}`,
        node.id,
      ),
    );
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
  updateAdminTarget();
}

function updateAdminTarget() {
  const remote = Boolean($("#adminTarget").value);
  $("#adminTargetHint").textContent = remote
    ? "Командата ще мине през LoRa remote-admin и изисква разрешен PKI public key."
    : "Командата се изпраща към директно свързаното радио.";
  $("#preserveNodePreferences").disabled = remote;
  if (remote) $("#preserveNodePreferences").checked = false;
  $("#preserveNodePreferencesHint").textContent = remote
    ? "Remote NodeDB не може да бъде прочетена предварително; запазването не е достъпно."
    : "MeshDesk ще запише текущите favorite/ignore флагове и ще ги приложи отново.";
}

function renderNodes(nodes) {
  state.nodes = nodes;
  const container = $("#nodes");
  fillDirectRecipients();
  fillConfigTargets();
  renderConversations();
  renderChat();

  if (!nodes.length) {
    $("#nodeCount").textContent = "0";
    $("#networkSummary").innerHTML = "";
    container.className = "nodes empty-state";
    container.textContent =
      state.connection === "connected" ? "Node database е празна." : "Няма връзка.";
    return;
  }

  const query = $("#nodeSearch").value.trim().toLocaleLowerCase("bg");
  const transportFilter = $("#nodeTransportFilter").value;
  const preferenceFilter = $("#nodePreferenceFilter").value;
  const showSelf = $("#showSelfNode").checked;
  const staleBefore = Date.now() / 1000 - 24 * 60 * 60;
  const selfNodes = showSelf ? nodes.filter((node) => node.is_self) : [];
  const filteredPeers = nodes.filter((node) => !node.is_self).filter((node) => {
    const matchesQuery =
      !query ||
      [node.long_name, node.short_name, node.id, node.hardware, node.role]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase("bg").includes(query));
    if (!matchesQuery) return false;
    if (preferenceFilter === "favorites" && !node.is_favorite) return false;
    if (preferenceFilter === "ignored" && !node.is_ignored) return false;
    if (
      preferenceFilter === "normal" &&
      (node.is_favorite || node.is_ignored)
    ) {
      return false;
    }
    if (transportFilter === "mqtt") return node.via_mqtt;
    if (transportFilter === "direct")
      return !node.via_mqtt && node.hops_away != null && Number(node.hops_away) === 0;
    if (transportFilter === "mesh")
      return !node.via_mqtt && Number(node.hops_away || 0) > 0;
    if (transportFilter === "stale")
      return !node.last_heard || node.last_heard < staleBefore;
    return true;
  });
  const sorters = {
    name: (left, right) => left.long_name.localeCompare(right.long_name, "bg"),
    recent: (left, right) => (right.last_heard || 0) - (left.last_heard || 0),
    signal: (left, right) => (right.snr ?? -999) - (left.snr ?? -999),
    hops: (left, right) => (left.hops_away ?? 999) - (right.hops_away ?? 999),
    battery: (left, right) =>
      (right.battery_level ?? -1) - (left.battery_level ?? -1),
  };
  filteredPeers.sort(sorters[$("#nodeSort").value] || sorters.recent);
  const filtered = [...selfNodes, ...filteredPeers];

  const directCount = nodes.filter(
    (node) => !node.via_mqtt && node.hops_away != null && Number(node.hops_away) === 0,
  ).length;
  const mqttCount = nodes.filter((node) => node.via_mqtt).length;
  const meshCount = nodes.filter(
    (node) => !node.via_mqtt && Number(node.hops_away || 0) > 0,
  ).length;
  $("#nodeCount").textContent =
    filtered.length === nodes.length ? String(nodes.length) : `${filtered.length}/${nodes.length}`;
  $("#networkSummary").innerHTML = `
    <span class="network-stat"><b>${nodes.length}</b> общо</span>
    <span class="network-stat"><b>${directCount}</b> директни</span>
    <span class="network-stat"><b>${meshCount}</b> през mesh</span>
    <span class="network-stat"><b>${mqttCount}</b> MQTT</span>
    <span class="network-stat"><b>${nodes.filter((node) => node.is_favorite).length}</b> любими</span>`;

  if (!filtered.length) {
    container.className = "nodes empty-state";
    container.textContent = "Няма възли, които отговарят на избраните филтри.";
    return;
  }
  container.className = "nodes";
  container.innerHTML = filtered
    .map((node) => {
      const battery =
        node.battery_level != null ? `${node.battery_level}%` : "—";
      const snr = node.snr != null ? `${Number(node.snr).toFixed(1)} dB` : "—";
      const hops = node.via_mqtt
        ? "MQTT"
        : node.hops_away == null
          ? "—"
          : Number(node.hops_away) === 0
            ? "direct"
            : String(node.hops_away);
      const channel = node.channel == null ? "—" : node.channel;
      const transportLabel = node.via_mqtt
        ? '<span class="node-badge mqtt">MQTT</span>'
        : node.hops_away != null && Number(node.hops_away) === 0
          ? '<span class="node-badge direct">● директен</span>'
          : node.hops_away != null
            ? `<span class="node-badge">${escapeHtml(node.hops_away)} hops</span>`
            : '<span class="node-badge">radio</span>';
      const preferenceControls = node.is_self
        ? `<span class="self-node-preference"
            title="Собственото радио не може да бъде favorite/ignored в собствената си NodeDB.">
            собствено радио</span>`
        : `<button type="button"
              class="node-preference ghost${node.is_favorite ? " active" : ""}"
              data-action="${node.is_favorite ? "unfavorite" : "favorite"}"
              data-node="${escapeHtml(node.id)}"
              title="${node.is_favorite ? "Премахни от любими" : "Добави в любими"}"
              aria-label="${node.is_favorite ? "Премахни от любими" : "Добави в любими"}">★</button>
            <button type="button"
              class="node-preference ignored ghost${node.is_ignored ? " active" : ""}"
              data-action="${node.is_ignored ? "unignore" : "ignore"}"
              data-node="${escapeHtml(node.id)}"
              title="${node.is_ignored ? "Спри игнорирането" : "Игнорирай възела"}"
              aria-label="${node.is_ignored ? "Спри игнорирането" : "Игнорирай възела"}">⊘</button>`;
      return `
        <article class="node-card${node.is_ignored ? " node-ignored" : ""}">
          <div class="node-avatar">${escapeHtml(node.short_name.slice(0, 4))}</div>
          <div class="node-name">
            <strong>${escapeHtml(node.long_name)}</strong>
            <span>${escapeHtml(node.id)} · ${escapeHtml(node.hardware || "unknown hw")}${
              node.role ? ` · ${escapeHtml(node.role)}` : ""
            }</span>
          </div>
          <div class="node-state">
            ${transportLabel}
            ${node.is_favorite ? '<span class="node-badge direct">★ любим</span>' : ""}
            ${node.is_ignored ? '<span class="node-badge ignored">⊘ игнориран</span>' : ""}
          </div>
          <div class="node-metrics">
            <div class="metric"><span>батерия</span><strong>${battery}</strong></div>
            <div class="metric"><span>последен SNR</span><strong>${snr}</strong></div>
            <div class="metric"><span>маршрут</span><strong>${escapeHtml(hops)}</strong></div>
            <div class="metric"><span>канал</span><strong>${escapeHtml(channel)}</strong></div>
            <div class="metric"><span>последно чут</span><strong>${formatAge(
              node.last_heard,
            )}</strong></div>
          </div>
          <div class="node-actions">
            ${preferenceControls}
            <button type="button" class="node-message ghost" data-node="${escapeHtml(
              node.id,
            )}" ${node.is_messageable ? "" : "disabled"}>Съобщение</button>
            <button type="button" class="node-quick-action ghost" data-action="traceroute"
              data-request-action="traceroute" data-default-label="Trace"
              data-node="${escapeHtml(node.id)}">Trace</button>
            <button type="button" class="node-quick-action ghost" data-action="telemetry"
              data-node="${escapeHtml(node.id)}">Telemetry</button>
            <button type="button" class="node-inspect ghost" data-node="${escapeHtml(
              node.id,
            )}">Подробности →</button>
          </div>
        </article>`;
    })
    .join("");
  container.querySelectorAll(".node-message").forEach((button) => {
    button.addEventListener("click", () => {
      const key = `direct:${button.dataset.node}`;
      state.chatMessages[key] ||= [];
      selectConversation(key);
      $("#messageText").focus();
      document.querySelector(".chat-panel").scrollIntoView({ behavior: "smooth" });
    });
  });
  container.querySelectorAll(".node-quick-action").forEach((button) => {
    button.addEventListener("click", () => {
      openNodeInspector(button.dataset.node);
      requestNodeAction(button.dataset.node, button.dataset.action);
    });
  });
  container.querySelectorAll(".node-preference").forEach((button) => {
    button.addEventListener("click", () =>
      requestNodeAction(button.dataset.node, button.dataset.action),
    );
  });
  container.querySelectorAll(".node-inspect").forEach((button) => {
    button.addEventListener("click", () => openNodeInspector(button.dataset.node));
  });
  applyRequestCooldowns();
}

function valueOrDash(value, suffix = "") {
  return value == null || value === "" ? "—" : `${value}${suffix}`;
}

function flattenMetrics(value, prefix = "") {
  const rows = [];
  Object.entries(value || {}).forEach(([key, item]) => {
    const label = prefix ? `${prefix} · ${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item)) {
      rows.push(...flattenMetrics(item, label));
    } else {
      rows.push([label, Array.isArray(item) ? item.join(", ") : item]);
    }
  });
  return rows;
}

function metricTable(value) {
  const rows = flattenMetrics(value);
  if (!rows.length) return '<p class="inspector-note">Няма налични стойности.</p>';
  return `<table class="metric-table">${rows
    .map(
      ([key, item]) =>
        `<tr><td>${escapeHtml(key.replaceAll("_", " "))}</td><td>${escapeHtml(
          valueOrDash(item),
        )}</td></tr>`,
    )
    .join("")}</table>`;
}

function neighborValue(value, camelCase, snakeCase) {
  return value?.[camelCase] ?? value?.[snakeCase];
}

function nodeIdFromNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return `!${(number >>> 0).toString(16).padStart(8, "0")}`;
}

function formatNeighborInterval(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "неизвестен";
  if (value % 3600 === 0) {
    const hours = value / 3600;
    return `${hours} ${hours === 1 ? "час" : "часа"} (${value} s)`;
  }
  if (value % 60 === 0) return `${value / 60} min (${value} s)`;
  return `${value} s`;
}

function neighborNodeLabel(nodeNumber) {
  const nodeId = nodeIdFromNumber(nodeNumber);
  const node = nodeId ? nodeForId(nodeId) : null;
  return {
    id: nodeId || valueOrDash(nodeNumber),
    name: node?.long_name || node?.short_name || "Непознат възел",
  };
}

function neighborInfoHtml(info, event) {
  if (!info || typeof info !== "object") {
    return '<p class="inspector-note">Отговорът не съдържа Neighbor Info.</p>';
  }
  const reportNodeNumber = neighborValue(info, "nodeId", "node_id");
  const senderNodeNumber = neighborValue(info, "lastSentById", "last_sent_by_id");
  const interval = neighborValue(
    info,
    "nodeBroadcastIntervalSecs",
    "node_broadcast_interval_secs",
  );
  const reportNode = neighborNodeLabel(reportNodeNumber);
  const senderNode = neighborNodeLabel(senderNodeNumber);
  const neighbors = Array.isArray(info.neighbors) ? info.neighbors : [];
  const senderExplanation =
    Number(reportNodeNumber) === Number(senderNodeNumber)
      ? "директен отчет от първоизточника"
      : "отчетът е препратен от друг възел";

  const rows = neighbors.length
    ? neighbors
        .map((neighbor) => {
          const nodeNumber = neighborValue(neighbor, "nodeId", "node_id");
          const node = neighborNodeLabel(nodeNumber);
          const snr = neighborValue(neighbor, "snr", "snr");
          const lastRx = neighborValue(neighbor, "lastRxTime", "last_rx_time");
          const neighborInterval = neighborValue(
            neighbor,
            "nodeBroadcastIntervalSecs",
            "node_broadcast_interval_secs",
          );
          const lastRxLabel = lastRx
            ? `${new Date(Number(lastRx) * 1000).toLocaleString()} · ${formatAge(
                Number(lastRx),
              )}`
            : "неизвестно";
          return `
            <tr>
              <td><strong>${escapeHtml(node.name)}</strong><small>${escapeHtml(
                node.id,
              )} · ${escapeHtml(nodeNumber)}</small></td>
              <td>${escapeHtml(snr == null ? "—" : `${Number(snr).toFixed(2)} dB`)}</td>
              <td>${escapeHtml(lastRxLabel)}</td>
              <td>${escapeHtml(formatNeighborInterval(neighborInterval))}</td>
            </tr>`;
        })
        .join("")
    : '<tr><td colspan="4">Възелът не е върнал записани съседи.</td></tr>';

  return `
    <div class="neighbor-summary">
      <div class="inspector-value"><span>Отчет на възел</span><strong>${escapeHtml(
        reportNode.name,
      )}</strong><small>${escapeHtml(reportNode.id)} · ${escapeHtml(
        reportNodeNumber,
      )}</small></div>
      <div class="inspector-value"><span>Последно изпратен от</span><strong>${escapeHtml(
        senderNode.name,
      )}</strong><small>${escapeHtml(senderNode.id)} · ${escapeHtml(
        senderExplanation,
      )}</small></div>
      <div class="inspector-value"><span>Broadcast interval</span><strong>${escapeHtml(
        formatNeighborInterval(interval),
      )}</strong></div>
      <div class="inspector-value"><span>Върнати съседи</span><strong>${escapeHtml(
        neighbors.length,
      )}</strong></div>
    </div>
    <div class="neighbor-table-wrap">
      <table class="neighbor-table">
        <thead><tr><th>Съсед</th><th>SNR</th><th>Последно приет</th><th>Интервал</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="inspector-note">Това са директно чуваните съседи според отчитащия
      възел, а не непременно всички възли по маршрут до него.</p>
    <details class="raw-details">
      <summary>Raw Neighbor Info packet</summary>
      <pre>${escapeHtml(JSON.stringify(event.packet || info, null, 2))}</pre>
    </details>`;
}

function routeHtml(route) {
  if (!route?.length) return '<p class="inspector-note">Маршрутът не е върнат.</p>';
  return `<div class="route-path">${route
    .map((hop) => {
      const node = nodeForId(hop.id);
      return `<span class="route-node" title="${escapeHtml(hop.id)}">
        ${escapeHtml(node?.short_name || hop.id.slice(-4))}
        ${hop.snr == null ? "" : `<small>${escapeHtml(hop.snr)} dB</small>`}
      </span>`;
    })
    .join("")}</div>`;
}

function operationLabel(event) {
  if (event.operation === "traceroute") return "Traceroute";
  if (event.operation === "position") return "Position";
  if (event.operation === "user_info") return "User Info";
  if (event.operation === "neighbor_info") return "Neighbor Info";
  if (event.operation === "favorite") return "Добавяне в любими";
  if (event.operation === "unfavorite") return "Премахване от любими";
  if (event.operation === "ignore") return "Игнориране на възел";
  if (event.operation === "unignore") return "Спиране на игнорирането";
  if (event.operation === "remote_config") return "Remote configuration";
  if (event.operation === "history_replay") return "Синхронизация на историята";
  if (event.operation === "administration") {
    const labels = {
      reboot: "Рестартиране",
      shutdown: "Изключване",
      reset_nodedb: "Изчистване на NodeDB",
      factory_reset_config: "Нулиране на конфигурацията",
      factory_reset_device: "Пълно фабрично нулиране",
    };
    return labels[event.admin_action] || "Администрация";
  }
  const names = {
    device: "Device telemetry",
    environment: "Environment telemetry",
    air_quality: "Air quality telemetry",
    power: "Power telemetry",
    local_stats: "Local statistics",
    host: "Host telemetry",
    pax: "PAX telemetry",
  };
  return names[event.telemetry_type] || "Telemetry";
}

function operationResultHtml(event) {
  const stateClass =
    event.kind === "operation_request" ? "pending" : event.success ? "success" : "failed";
  let body = "";
  if (event.kind === "operation_request") {
    body =
      event.operation === "history_replay"
        ? `<p>Поискани до ${escapeHtml(event.max_messages)} съобщения за ${
            escapeHtml(event.window)
          } минути · marker ${escapeHtml(event.last_request)}</p>`
        : event.operation === "administration"
          ? `<p>Административната команда е приета за изпращане.</p>`
          : `<p>Заявката е изпратена · channel ${escapeHtml(
              event.channel,
            )} · hop limit ${escapeHtml(event.hop_limit)}</p>`;
  } else if (!event.success) {
    body = `<p>${escapeHtml(event.error || "Няма отговор от възела")}</p>`;
  } else if (event.operation === "traceroute") {
    body = `
      <p>Маршрут към възела</p>
      ${routeHtml(event.result?.route_towards)}
      <p>Обратен маршрут</p>
      ${routeHtml(event.result?.route_back)}`;
  } else if (event.operation === "telemetry") {
    body = metricTable(event.result?.telemetry);
  } else if (event.operation === "position") {
    body = metricTable(event.result?.position);
  } else if (event.operation === "user_info") {
    body = metricTable(event.result?.user);
  } else if (event.operation === "neighbor_info") {
    body = neighborInfoHtml(event.result?.neighbor_info, event);
  } else if (event.operation === "remote_config") {
    body = `<p>Секция „${escapeHtml(event.section)}“ е заредена чрез PKI admin.</p>`;
  } else if (event.operation === "administration") {
    body = `<p>Командата е изпратена към устройството.${
      event.result?.restored_preferences
        ? ` Възстановени preference флагове: ${escapeHtml(
            event.result.restored_preferences,
          )}.`
        : ""
    }</p>`;
  } else if (event.operation === "history_replay") {
    body = "<p>Радиото прие заявката за синхронизация.</p>";
  } else if (
    ["favorite", "unfavorite", "ignore", "unignore"].includes(event.operation)
  ) {
    const managed = nodeForId(event.managed_node);
    const managedLabel =
      managed?.long_name || event.managed_node || state.status?.profile_name || "локалното радио";
    const acknowledgment = event.result?.acknowledgment || "неизвестен";
    body = event.remote
      ? `<p>Командата е приета от NodeDB на ${escapeHtml(managedLabel)}.</p>
        <div class="operation-meta">
          <span><small>Транспортен резултат</small><strong>${escapeHtml(
            acknowledgment.toUpperCase(),
          )}</strong></span>
          <span><small>Desired state</small><strong>непроверено</strong></span>
          ${
            event.result?.session_refreshed
              ? "<span><small>Admin session</small><strong>подновена</strong></span>"
              : ""
          }
        </div>`
      : `<p>NodeDB на локалното радио е обновена.</p>
        <div class="operation-meta">
          <span><small>Състояние</small><strong>локално приложено</strong></span>
        </div>`;
  } else {
    body = "<p>Node database е обновена.</p>";
  }
  if (
    event.kind === "operation_result" &&
    !event.success &&
    ["favorite", "unfavorite", "ignore", "unignore"].includes(event.operation)
  ) {
    const acknowledgment = event.result?.acknowledgment || "error";
    body += `<div class="operation-meta">
      <span><small>Резултат</small><strong>${escapeHtml(
        acknowledgment.toUpperCase(),
      )}</strong></span>
      <span><small>Desired state</small><strong>непроменено/неизвестно</strong></span>
    </div>`;
  }
  return `<article class="operation-card ${stateClass}">
    <div class="operation-heading">
      <strong>${escapeHtml(operationLabel(event))}</strong>
      <time>${escapeHtml(messageTime(event.time))}</time>
    </div>
    ${body}
  </article>`;
}

function showInspector() {
  $("#inspectorBackdrop").classList.remove("hidden");
  $("#inspectorPanel").setAttribute("aria-hidden", "false");
  document.body.classList.add("inspector-open");
}

function closeInspector() {
  state.inspector = null;
  $("#inspectorBackdrop").classList.add("hidden");
  $("#inspectorPanel").setAttribute("aria-hidden", "true");
  document.body.classList.remove("inspector-open");
}

function openNodeInspector(nodeId) {
  state.inspector = { type: "node", nodeId, managedNodeId: "" };
  renderInspector();
  showInspector();
}

function nodeOperations(nodeId) {
  return state.eventLog
    .filter(
      (event) =>
        ["operation_request", "operation_result"].includes(event.kind) &&
        event.target?.toLowerCase() === nodeId.toLowerCase(),
    )
    .slice(-10)
    .reverse();
}

function nodeDbActionControls(node, managedNodeId = "") {
  const targetsItself =
    (!managedNodeId && node.is_self) ||
    (managedNodeId && managedNodeId.toLowerCase() === node.id.toLowerCase());
  if (targetsItself) {
    return `
      <div class="nodedb-context self">
        <strong>Собствен възел</strong>
        <span>Favorite/ignore не се прилага за радиото в собствената му NodeDB.
          То не може да бъде изхвърлено или игнорирано като remote peer.</span>
      </div>`;
  }
  if (!managedNodeId) {
    return `
      <div class="nodedb-context known">
        <strong>Локално състояние</strong>
        <span>Любим: ${node.is_favorite ? "да" : "не"} · Игнориран: ${
          node.is_ignored ? "да" : "не"
        }</span>
      </div>
      <div class="inspector-actions">
        <button type="button" class="ghost inspector-action"
          data-action="${node.is_favorite ? "unfavorite" : "favorite"}">${
            node.is_favorite ? "Премахни от любими" : "Добави в любими"
          }</button>
        <button type="button" class="ghost inspector-action"
          data-action="${node.is_ignored ? "unignore" : "ignore"}">${
            node.is_ignored ? "Спри игнорирането" : "Игнорирай възела"
          }</button>
      </div>`;
  }
  const managed = nodeForId(managedNodeId);
  return `
    <div class="nodedb-context unknown">
      <strong>Remote състояние: неизвестно</strong>
      <span>Meshtastic admin протоколът не позволява прочитане на NodeDB на
        ${escapeHtml(managed?.long_name || managedNodeId)}.</span>
    </div>
    <div class="remote-nodedb-actions">
      <div>
        <span>Любими</span>
        <div class="inspector-actions">
          <button type="button" class="ghost inspector-action"
            data-action="favorite">Добави</button>
          <button type="button" class="ghost inspector-action"
            data-action="unfavorite">Премахни</button>
        </div>
      </div>
      <div>
        <span>Игнориране</span>
        <div class="inspector-actions">
          <button type="button" class="ghost inspector-action"
            data-action="ignore">Игнорирай</button>
          <button type="button" class="ghost inspector-action"
            data-action="unignore">Спри</button>
        </div>
      </div>
    </div>`;
}

function renderNodeInspector(node) {
  $("#inspectorEyebrow").textContent = "NODE INSPECTOR";
  $("#inspectorTitle").textContent = node.long_name;
  $("#inspectorSubtitle").textContent =
    `${node.short_name} · ${node.id} · ${node.hardware || "unknown hardware"}`;
  const operations = nodeOperations(node.id);
  const routeType = node.via_mqtt
    ? "MQTT"
    : node.hops_away == null
      ? "неизвестен"
      : Number(node.hops_away) === 0
        ? "директен peer"
        : `${node.hops_away} radio hops`;
  const managedNodeId = state.inspector?.managedNodeId || "";
  const managedNodeOptions = [
    `<option value="">Локално: ${escapeHtml(
      state.status?.profile_name || state.profileId || "радио",
    )}</option>`,
    ...state.nodes.map(
      (candidate) =>
        `<option value="${escapeHtml(candidate.id)}" ${
          candidate.id.toLowerCase() === managedNodeId.toLowerCase() ? "selected" : ""
        }>Remote: ${escapeHtml(
          candidate.long_name,
        )} · ${escapeHtml(candidate.id)}</option>`,
    ),
  ].join("");
  $("#inspectorContent").innerHTML = `
    <section class="inspector-section">
      <div class="inspector-section-title">
        <h3>Действия</h3>
        <span class="node-badge ${node.via_mqtt ? "mqtt" : ""}">${escapeHtml(
          routeType,
        )}</span>
      </div>
      <div class="inspector-actions">
        <button type="button" class="secondary inspector-action"
          data-action="traceroute" data-request-action="traceroute"
          data-default-label="Traceroute" data-node="${escapeHtml(node.id)}">Traceroute</button>
        <div class="telemetry-request">
          <select id="inspectorTelemetryType">
            <option value="device">Device metrics</option>
            <option value="environment">Environment</option>
            <option value="air_quality">Air quality</option>
            <option value="power">Power</option>
            <option value="local_stats">Local stats</option>
            <option value="host">Host metrics</option>
            <option value="pax">PAX metrics</option>
          </select>
          <button type="button" class="secondary inspector-action"
            data-action="telemetry">Telemetry</button>
        </div>
        <button type="button" class="secondary inspector-action"
          data-action="position">Position</button>
        <button type="button" class="secondary inspector-action"
          data-action="user_info">User Info</button>
        <button type="button" class="secondary inspector-action"
          data-action="neighbor_info" data-request-action="neighbor_info"
          data-default-label="Neighbor Info" data-node="${escapeHtml(
            node.id,
          )}">Neighbor Info</button>
        <button type="button" class="ghost inspector-message"
          ${node.is_messageable ? "" : "disabled"}>Съобщение</button>
        <button type="button" class="ghost inspector-admin">Remote admin</button>
      </div>
      <p class="inspector-note">Traceroute използва общ 30 s cooldown за mesh-а.
        Neighbor Info използва 180 s cooldown само за този възел. Оставащото
        време се показва върху бутона; chat трафикът не се блокира.</p>
    </section>

    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Node database</h3></div>
      <label class="inspector-admin-target">
        Промени NodeDB на
        <select id="inspectorNodeDbTarget">${managedNodeOptions}</select>
      </label>
      <div id="inspectorNodeDbActions">
        ${nodeDbActionControls(node, managedNodeId)}
      </div>
      <p class="inspector-note">Remote командите минават през PKI admin. ACK
        потвърждава командата, но не означава, че MeshDesk може да прочете
        последващото remote NodeDB състояние.</p>
    </section>

    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Radio и маршрут</h3></div>
      <div class="inspector-grid">
        <div class="inspector-value"><span>Транспорт</span><strong>${escapeHtml(
          routeType,
        )}</strong></div>
        <div class="inspector-value"><span>Последен SNR</span><strong>${escapeHtml(
          valueOrDash(node.snr, node.snr == null ? "" : " dB"),
        )}</strong></div>
        <div class="inspector-value"><span>Channel index</span><strong>${escapeHtml(
          valueOrDash(node.channel),
        )}</strong></div>
        <div class="inspector-value"><span>Последно чут</span><strong>${escapeHtml(
          formatAge(node.last_heard),
        )}</strong></div>
        <div class="inspector-value"><span>Role</span><strong>${escapeHtml(
          valueOrDash(node.role),
        )}</strong></div>
        <div class="inspector-value"><span>Node number</span><strong>${escapeHtml(
          valueOrDash(node.num),
        )}</strong></div>
      </div>
      <p class="inspector-note">SNR е стойност за последния видян радио линк. Пълният
        път и SNR по хопове се показват само след успешен traceroute.</p>
    </section>

    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Device telemetry</h3></div>
      ${metricTable(node.device_metrics)}
    </section>

    ${
      Object.keys(node.environment_metrics || {}).length
        ? `<section class="inspector-section"><div class="inspector-section-title">
          <h3>Environment</h3></div>${metricTable(node.environment_metrics)}</section>`
        : ""
    }
    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Позиция</h3></div>
      ${metricTable(node.position)}
    </section>

    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Последни заявки</h3></div>
      ${
        operations.length
          ? operations.map(operationResultHtml).join("")
          : '<p class="inspector-note">Все още няма diagnostic заявки към този възел.</p>'
      }
    </section>

    <details class="raw-details">
      <summary>Пълен raw node record</summary>
      <pre>${escapeHtml(JSON.stringify(node.raw || node, null, 2))}</pre>
    </details>`;

  const bindActionButtons = (root) => {
    root.querySelectorAll(".inspector-action").forEach((button) => {
      button.addEventListener("click", () => {
        const telemetryType =
          button.dataset.action === "telemetry"
            ? $("#inspectorTelemetryType").value
            : "device";
        const isNodeDbAction = ["favorite", "unfavorite", "ignore", "unignore"].includes(
          button.dataset.action,
        );
        requestNodeAction(
          node.id,
          button.dataset.action,
          telemetryType,
          isNodeDbAction ? $("#inspectorNodeDbTarget").value : null,
        );
      });
    });
  };
  bindActionButtons($("#inspectorContent"));
  applyRequestCooldowns();
  $("#inspectorNodeDbTarget").addEventListener("change", () => {
    const selectedTarget = $("#inspectorNodeDbTarget").value;
    if (state.inspector?.type === "node") {
      state.inspector.managedNodeId = selectedTarget;
    }
    const actions = $("#inspectorNodeDbActions");
    actions.innerHTML = nodeDbActionControls(node, selectedTarget);
    bindActionButtons(actions);
  });
  $(".inspector-message").addEventListener("click", () => {
    const key = `direct:${node.id}`;
    state.chatMessages[key] ||= [];
    selectConversation(key);
    closeInspector();
    document.querySelector(".chat-panel").scrollIntoView({ behavior: "smooth" });
    $("#messageText").focus();
  });
  $(".inspector-admin").addEventListener("click", async () => {
    $("#configTarget").value = node.id;
    $("#remoteConfigControls").classList.remove("hidden");
    $("#configPanel").open = true;
    selectSettingsView("config");
    state.activeConfig = null;
    closeInspector();
    await refreshConfig();
    $("#configPanel").scrollIntoView({ behavior: "smooth" });
  });
}

function packetValue(packet, camel, snake) {
  return packet?.[camel] ?? packet?.[snake];
}

function renderMessageInspector(message) {
  const event = message.sourceEvent || {};
  const packet = event.packet || {};
  const decoded = packet.decoded || {};
  const from = event.from || packet.fromId || packet.from;
  const to = event.to || packet.toId || packet.to;
  const hopStart = event.hop_start ?? packetValue(packet, "hopStart", "hop_start");
  const hopLimit = event.hop_limit ?? packetValue(packet, "hopLimit", "hop_limit");
  const hops =
    event.hops_travelled ??
    (Number.isInteger(hopStart) && Number.isInteger(hopLimit)
      ? hopStart - hopLimit
      : null);
  const viaMqtt =
    Boolean(event.via_mqtt) || Boolean(packetValue(packet, "viaMqtt", "via_mqtt"));
  const rssi = event.rssi ?? packetValue(packet, "rxRssi", "rx_rssi");
  const snr = event.snr ?? packetValue(packet, "rxSnr", "rx_snr");
  const gateway = packetValue(packet, "gatewayId", "gateway_id");
  const relay = event.relay_node ?? packetValue(packet, "relayNode", "relay_node");
  const transport = viaMqtt
    ? "MQTT"
    : hops == null
      ? "LoRa / неизвестен маршрут"
      : hops === 0
        ? "Direct LoRa peer"
        : `LoRa · ${hops} hops`;

  $("#inspectorEyebrow").textContent = "PACKET INSPECTOR";
  $("#inspectorTitle").textContent =
    message.direction === "outgoing" ? "Изпратено съобщение" : "Получено съобщение";
  $("#inspectorSubtitle").textContent = `${messageTime(message.time)} · packet ${
    message.packetId ?? packet.id ?? "—"
  }`;
  $("#inspectorContent").innerHTML = `
    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Съдържание</h3></div>
      <div class="message-bubble">${escapeHtml(message.text)}</div>
    </section>
    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Маршрут и транспорт</h3>
        <span class="node-badge ${viaMqtt ? "mqtt" : ""}">${escapeHtml(transport)}</span>
      </div>
      <div class="inspector-grid">
        <div class="inspector-value"><span>От</span><strong>${escapeHtml(
          valueOrDash(from),
        )}</strong></div>
        <div class="inspector-value"><span>До</span><strong>${escapeHtml(
          valueOrDash(to),
        )}</strong></div>
        <div class="inspector-value"><span>Изминати хопове</span><strong>${escapeHtml(
          valueOrDash(hops),
        )}</strong></div>
        <div class="inspector-value"><span>Hop start / remaining</span><strong>${escapeHtml(
          `${valueOrDash(hopStart)} / ${valueOrDash(hopLimit)}`,
        )}</strong></div>
        <div class="inspector-value"><span>MQTT gateway</span><strong>${escapeHtml(
          viaMqtt ? gateway || "не е предоставен в MeshPacket" : "—",
        )}</strong></div>
        <div class="inspector-value"><span>Relay node</span><strong>${escapeHtml(
          valueOrDash(relay),
        )}</strong></div>
        <div class="inspector-value"><span>Transport mechanism</span><strong>${escapeHtml(
          valueOrDash(
            event.transport_mechanism ||
              packetValue(packet, "transportMechanism", "transport_mechanism"),
          ),
        )}</strong></div>
      </div>
      <p class="inspector-note">Обикновеният пакет показва общия брой хопове, но не
        имената на всички междинни възли. За точния път използвай Traceroute към peer-а.</p>
    </section>
    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Последен радио линк</h3></div>
      <div class="inspector-grid">
        <div class="inspector-value"><span>RSSI</span><strong>${escapeHtml(
          valueOrDash(rssi, rssi == null ? "" : " dBm"),
        )}</strong></div>
        <div class="inspector-value"><span>SNR</span><strong>${escapeHtml(
          valueOrDash(snr, snr == null ? "" : " dB"),
        )}</strong></div>
      </div>
    </section>
    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Packet metadata</h3></div>
      <div class="inspector-grid">
        <div class="inspector-value"><span>Packet ID</span><strong>${escapeHtml(
          valueOrDash(message.packetId ?? packet.id),
        )}</strong></div>
        <div class="inspector-value"><span>Channel</span><strong>${escapeHtml(
          valueOrDash(event.channel ?? packet.channel),
        )}</strong></div>
        <div class="inspector-value"><span>Port</span><strong>${escapeHtml(
          valueOrDash(event.portnum || decoded.portnum),
        )}</strong></div>
        <div class="inspector-value"><span>Priority</span><strong>${escapeHtml(
          valueOrDash(packet.priority),
        )}</strong></div>
        <div class="inspector-value"><span>Request ID</span><strong>${escapeHtml(
          valueOrDash(event.request_id ?? decoded.requestId),
        )}</strong></div>
        <div class="inspector-value"><span>Reply ID</span><strong>${escapeHtml(
          valueOrDash(event.reply_id ?? decoded.replyId),
        )}</strong></div>
        <div class="inspector-value"><span>Encrypted / PKI</span><strong>${escapeHtml(
          `${packet.encrypted ? "yes" : "no"} / ${
            packetValue(packet, "pkiEncrypted", "pki_encrypted") ? "yes" : "no"
          }`,
        )}</strong></div>
        <div class="inspector-value"><span>ACK</span><strong>${escapeHtml(
          message.wantAck ? message.delivery || "pending" : "not requested",
        )}</strong></div>
      </div>
    </section>
    <details class="raw-details">
      <summary>Пълен raw packet</summary>
      <pre>${escapeHtml(
        JSON.stringify({ packet_event: event, delivery_event: message.deliveryEvent }, null, 2),
      )}</pre>
    </details>`;
}

function openMessageInspector(eventId) {
  let selected = null;
  Object.values(state.chatMessages).some((messages) => {
    selected = messages.find((message) => message.eventId === eventId);
    return Boolean(selected);
  });
  if (!selected) return;
  state.inspector = { type: "message", eventId };
  renderMessageInspector(selected);
  showInspector();
}

function renderInspector() {
  if (!state.inspector) return;
  if (state.inspector.type === "node") {
    const node = nodeForId(state.inspector.nodeId);
    if (node) renderNodeInspector(node);
  } else {
    openMessageInspector(state.inspector.eventId);
  }
}

async function requestNodeAction(
  nodeId,
  action,
  telemetryType = "device",
  managedNodeId = null,
) {
  const preferenceAction = ["favorite", "unfavorite", "ignore", "unignore"].includes(
    action,
  );
  if (managedNodeId && preferenceAction) {
    const managed = nodeForId(managedNodeId);
    const subject = nodeForId(nodeId);
    const instruction = {
      favorite: "добави в любими",
      unfavorite: "премахни от любими",
      ignore: "игнорирай",
      unignore: "спри игнорирането на",
    }[action];
    if (
      !confirm(
        `NodeDB на ${managed?.long_name || managedNodeId}: ${instruction} ` +
          `${subject?.long_name || nodeId} (${nodeId})? ` +
          "Текущото remote състояние не може да бъде прочетено.",
      )
    ) {
      return;
    }
  } else if (
    action === "ignore" &&
    !confirm("Радиото може да спре да обработва пакети от този възел. Да продължа ли?")
  ) {
    return;
  }
  try {
    await api("/api/node-actions", {
      method: "POST",
      body: JSON.stringify({
        node_id: nodeId,
        action,
        telemetry_type: telemetryType,
        channel: Number($("#channel").value || 0),
        managed_node_id: managedNodeId || null,
      }),
    });
    if (!managedNodeId) {
      const node = nodeForId(nodeId);
      if (node && ["favorite", "unfavorite", "ignore", "unignore"].includes(action)) {
        if (action === "favorite") node.is_favorite = true;
        if (action === "unfavorite") node.is_favorite = false;
        if (action === "ignore") node.is_ignored = true;
        if (action === "unignore") node.is_ignored = false;
        renderNodes(state.nodes);
        if (state.inspector?.type === "node") renderInspector();
      }
    }
    toast(
      managedNodeId && preferenceAction
        ? `${operationLabel({
            operation: action,
            telemetry_type: telemetryType,
          })}: remote командата получи ACK; състоянието остава неизвестно`
        : preferenceAction
          ? `${operationLabel({
              operation: action,
              telemetry_type: telemetryType,
            })} е приложено`
          : `${operationLabel({
              operation: action,
              telemetry_type: telemetryType,
            })}: заявката е изпратена`,
    );
  } catch (error) {
    if (error.details?.code === "request_cooldown") {
      const seconds = Math.max(1, Math.ceil(error.details.remaining_seconds || 0));
      toast(
        `${operationLabel({ operation: action, telemetry_type: telemetryType })}: ` +
          `изчакай още ${seconds} секунди`,
        true,
      );
      setTimeout(refreshStatus, 100);
    } else {
      toast(error.message, true);
    }
  }
}

function renderChannels(channels) {
  state.channels = channels;
  const select = $("#channel");
  const current = select.value;
  select.innerHTML = "";
  if (!channels.length) {
    select.add(new Option("0 · Primary", "0"));
    if (
      !state.selectedConversation &&
      state.connection === "connected" &&
      state.profileId
    ) {
      state.selectedConversation = "channel:0";
    }
    renderConversations();
    renderChat();
    return;
  }
  channels.forEach((channel) => {
    const flags = [
      channel.role,
      channel.encrypted ? "encrypted" : "open",
      channel.uplink_enabled ? "uplink" : "",
    ]
      .filter(Boolean)
      .join(", ");
    select.add(new Option(`${channel.index} · ${channel.name} (${flags})`, channel.index));
  });
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
  if (!state.selectedConversation && channels.length) {
    state.selectedConversation = `channel:${channels[0].index}`;
  }
  renderConversations();
  renderChat();
}

async function refreshChannels() {
  try {
    const { channels } = await api("/api/channels");
    renderChannels(channels);
  } catch (error) {
    toast(error.message, true);
  }
}

function bytesToBase64(bytes) {
  return btoa(String.fromCharCode(...bytes));
}

function parseChannelPsk(value) {
  const raw = String(value || "").trim();
  if (!raw) throw new Error("Въведи PSK");
  if (raw.startsWith("0x")) {
    const hex = raw.slice(2);
    if (!hex || hex.length % 2 || !/^[0-9a-f]+$/i.test(hex)) {
      throw new Error("Hex PSK трябва да съдържа четен брой hex знаци след 0x");
    }
    return Uint8Array.from(hex.match(/.{2}/g).map((part) => Number.parseInt(part, 16)));
  }
  const encoded = raw.startsWith("base64:") ? raw.slice(7) : raw;
  if (
    !encoded ||
    encoded.length % 4 === 1 ||
    !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)
  ) {
    throw new Error("PSK трябва да е валиден Base64 или 0x hex");
  }
  try {
    const binary = atob(encoded);
    const normalized = btoa(binary).replace(/=+$/, "");
    if (encoded.replace(/=+$/, "") !== normalized) {
      throw new Error("invalid base64");
    }
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  } catch {
    throw new Error("PSK трябва да е валиден Base64 или 0x hex");
  }
}

function channelPskAssessment(bytes, mode = "") {
  if (mode === "none" || (bytes.length === 1 && bytes[0] === 0)) {
    return { className: "danger", text: "Без криптиране · всеки може да прочете трафика" };
  }
  if (bytes.length === 1) {
    return {
      className: "warning",
      text: "Публично известен Meshtastic marker · подходящ само за public/test канал",
    };
  }
  if (bytes.length === 16) {
    return { className: "secure", text: "AES-128 · защитен custom ключ" };
  }
  if (bytes.length === 32) {
    return { className: "secure", text: "AES-256 · препоръчителен за private канал" };
  }
  return {
    className: "danger",
    text: `Невалиден размер: ${bytes.length} bytes · допустими са 1, 16 или 32`,
  };
}

function secureRandomChannelPsk(size) {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return bytesToBase64(bytes);
}

function updateNewChannelPskStatus() {
  const status = $("#channelPskStatus");
  const mode = $("#channelPskMode").value;
  const input = $("#channelPsk");
  const confirmation = $("#channelPskConfirm");
  try {
    const bytes = parseChannelPsk(input.value);
    const assessment = channelPskAssessment(bytes, mode);
    input.setAttribute("aria-invalid", String(assessment.className === "danger"));
    if (mode === "custom") {
      if (!confirmation.value.trim()) {
        confirmation.setAttribute("aria-invalid", "true");
        status.className = "channel-psk-status warning";
        status.textContent = `${assessment.text} · повтори ключа за потвърждение`;
        return;
      }
      const repeated = parseChannelPsk(confirmation.value);
      const matches =
        bytes.length === repeated.length &&
        bytes.every((value, index) => value === repeated[index]);
      confirmation.setAttribute("aria-invalid", String(!matches));
      if (!matches) {
        status.className = "channel-psk-status danger";
        status.textContent = "Custom PSK и потвърждението не съвпадат";
        return;
      }
    } else {
      confirmation.removeAttribute("aria-invalid");
    }
    status.className = `channel-psk-status ${assessment.className}`;
    status.textContent = `${assessment.text} · ${bytes.length} bytes${
      mode === "custom" ? " · потвърден" : ""
    }`;
  } catch (error) {
    input.setAttribute("aria-invalid", "true");
    if (mode === "custom") confirmation.setAttribute("aria-invalid", "true");
    status.className = "channel-psk-status danger";
    status.textContent = error.message;
  }
}

function configureChannelPskEditor({ reset = false } = {}) {
  const mode = $("#channelPskMode").value;
  const workbench = $("#channelPskWorkbench");
  const input = $("#channelPsk");
  const simpleRow = $("#channelSimpleRow");
  const confirmRow = $("#channelPskConfirmRow");
  const generateButton = $("#generateChannelPsk");
  workbench.classList.toggle("hidden", mode === "unchanged");
  if (mode === "unchanged") return;

  simpleRow.classList.toggle("hidden", mode !== "simple");
  confirmRow.classList.toggle("hidden", mode !== "custom");
  generateButton.classList.toggle(
    "hidden",
    !["random128", "random256"].includes(mode),
  );
  input.readOnly = mode !== "custom";
  input.placeholder =
    mode === "custom" ? "Base64, base64:… или 0x…" : "Base64 PSK";

  if (reset) {
    if (mode === "random256") input.value = secureRandomChannelPsk(32);
    else if (mode === "random128") input.value = secureRandomChannelPsk(16);
    else if (mode === "default") input.value = "AQ==";
    else if (mode === "none") input.value = "AA==";
    else if (mode === "simple") {
      input.value = bytesToBase64(
        Uint8Array.of(Number($("#channelSimpleIndex").value) + 1),
      );
    } else input.value = "";
    $("#channelPskConfirm").value = "";
  }
  updateNewChannelPskStatus();
}

async function copyChannelSecret(value, label = "PSK") {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    toast(`${label} е копиран. Изчисти clipboard-а след споделяне.`);
  } catch {
    toast("Браузърът не разреши достъп до clipboard", true);
  }
}

async function revealCurrentChannelPsk(slot) {
  const input = $("#channelCurrentPsk");
  const button = $("#revealCurrentChannelPsk");
  const copyButton = $("#copyCurrentChannelPsk");
  const status = $("#channelCurrentPskStatus");
  if (input.value) {
    input.value = "";
    input.type = "password";
    status.textContent = "Текущият ключ е скрит и премахнат от UI паметта.";
    status.className = "channel-psk-status";
    copyButton.disabled = true;
    button.textContent = "Покажи текущия PSK";
    return;
  }
  if (
    !confirm(
      `Да покажа текущия PSK за channel ${slot.index}? Всеки с този ключ може да чете трафика на канала.`,
    )
  ) {
    return;
  }
  try {
    const data = await api(`/api/channel-slots/${slot.index}/psk`, {
      cache: "no-store",
    });
    input.value = data.psk_base64;
    input.type = "text";
    const assessment = channelPskAssessment(
      parseChannelPsk(data.psk_base64 || "AA=="),
      data.encrypted ? "" : "none",
    );
    status.className = `channel-psk-status ${assessment.className}`;
    status.textContent = `${assessment.text} · Base64 · ${data.psk_state}`;
    copyButton.disabled = false;
    button.textContent = "Скрий текущия PSK";
  } catch (error) {
    toast(`PSK: ${error.message}`, true);
  }
}

function renderChannelEditor(slot) {
  const form = $("#channelEditor");
  if (!slot) {
    form.className = "channel-editor empty-state";
    form.textContent =
      state.connection === "connected"
        ? "Избери channel slot."
        : "Свържи устройство, за да редактираш каналите.";
    return;
  }
  const isPrimary = slot.index === 0;
  const role = slot.enabled ? slot.role : "SECONDARY";
  form.className = "channel-editor";
  form.innerHTML = `
    <div class="channel-editor-head">
      <div>
        <p class="eyebrow">CHANNEL SLOT ${escapeHtml(slot.index)}</p>
        <h3>${escapeHtml(slot.display_name)}</h3>
        <p>${slot.enabled ? `${slot.role} · ${slot.psk_state}` : "Свободен slot"}</p>
      </div>
      <span class="node-badge ${slot.encrypted ? "direct" : ""}">
        ${slot.encrypted ? "encrypted" : "open"}
      </span>
    </div>
    <div class="channel-editor-grid">
      <label>
        <span class="config-field-label">Role ${helpTrigger(
          "Slot 0 винаги е PRIMARY. Допълнителните активни slots са SECONDARY; DISABLED премахва избрания Secondary канал.",
          "Помощ за channel role",
        )}</span>
        <select id="channelRole" ${isPrimary ? "disabled" : ""}>
          ${
            isPrimary
              ? '<option value="PRIMARY">PRIMARY</option>'
              : `<option value="SECONDARY" ${
                  role === "SECONDARY" ? "selected" : ""
                }>SECONDARY</option>
                <option value="DISABLED">DISABLED / премахни</option>`
          }
        </select>
      </label>
      <label>
        <span class="config-field-label">Име ${helpTrigger(
          "Име до 10 знака. Трябва да е уникално сред активните канали и да съвпада при останалите участници.",
          "Помощ за името на канала",
        )}</span>
        <input id="channelName" maxlength="10" value="${escapeHtml(slot.name || "")}"
          placeholder="${isPrimary ? "Primary (по желание)" : "до 10 знака"}">
      </label>
      <label>
        <span class="config-field-label">PSK действие ${helpTrigger(
          "За private канал използвай random AES-256 или AES-128. Default и simple са публично известни ключове, а none не криптира трафика.",
          "Помощ за channel PSK",
        )}</span>
        <select id="channelPskMode">
          <option value="unchanged" ${slot.enabled ? "" : "disabled"}>Запази текущия</option>
          <option value="random256" ${slot.enabled ? "" : "selected"}>Random AES-256 · препоръчително</option>
          <option value="random128">Random AES-128 · по-кратък</option>
          <option value="custom">Custom Base64 / hex</option>
          <option value="simple">Simple 0–254 · публичен/слаб</option>
          <option value="default">Meshtastic default · публичен/слаб</option>
          <option value="none">Без криптиране</option>
        </select>
      </label>
      <label>
        <span class="config-field-label">Position precision ${helpTrigger(
          "Контролира точността на позицията, споделяна в този канал. По-ниска точност пази повече location privacy.",
          "Помощ за channel position precision",
        )}</span>
        <input id="channelPositionPrecision" type="number" min="0" max="32"
          value="${escapeHtml(slot.position_precision ?? 0)}">
      </label>
      <div class="channel-editor-flags">
        <label class="checkbox">
          <input id="channelUplink" type="checkbox" ${
            slot.uplink_enabled ? "checked" : ""
          }> MQTT uplink
          ${helpTrigger(
            "Позволява пакетите от този LoRa канал да бъдат качвани към MQTT от подходящ gateway.",
            "Помощ за MQTT uplink",
          )}
        </label>
        <label class="checkbox">
          <input id="channelDownlink" type="checkbox" ${
            slot.downlink_enabled ? "checked" : ""
          }> MQTT downlink
          ${helpTrigger(
            "Позволява MQTT пакетите за този канал да влизат в LoRa mesh-а. Използвай внимателно заради airtime и privacy.",
            "Помощ за MQTT downlink",
          )}
        </label>
      </div>
      <div id="channelPskWorkbench" class="channel-psk-workbench wide hidden">
        <label id="channelSimpleRow" class="hidden">
          <span class="config-field-label">Simple key ${helpTrigger(
            "simple0–simple254 са compact protobuf markers за публично известни AES-128 ключове. Те не осигуряват private комуникация.",
            "Помощ за simple PSK",
          )}</span>
          <select id="channelSimpleIndex">
            ${Array.from(
              { length: 255 },
              (_, index) => `<option value="${index}">simple${index}</option>`,
            ).join("")}
          </select>
        </label>
        <label>
          <span class="config-field-label">Нов PSK / preview ${helpTrigger(
            "Показва точната Base64 стойност за споделяне. При custom може да въведеш Base64, base64:… или 0x hex; допустими са 1, 16 и 32 bytes.",
            "Помощ за PSK preview",
          )}</span>
          <input id="channelPsk" type="password" autocomplete="off"
            autocapitalize="none" spellcheck="false">
        </label>
        <label id="channelPskConfirmRow" class="hidden">
          Потвърди custom PSK
          <input id="channelPskConfirm" type="password" autocomplete="off"
            autocapitalize="none" spellcheck="false">
        </label>
        <div class="channel-psk-actions">
          <button id="generateChannelPsk" type="button" class="ghost hidden">
            Генерирай отново
          </button>
          <button id="toggleChannelPsk" type="button" class="ghost">Покажи</button>
          <button id="copyChannelPsk" type="button" class="ghost">Копирай Base64</button>
        </div>
        <p id="channelPskStatus" class="channel-psk-status"></p>
      </div>
      ${
        slot.enabled
          ? `<div class="channel-current-psk wide">
              <div>
                <strong>Текущ PSK</strong>
                <p>Не се зарежда автоматично. Reveal отговаря с no-store и стойността
                  се изчиства при hide, смяна на slot или disconnect.</p>
              </div>
              <input id="channelCurrentPsk" type="password" readonly
                autocomplete="off" aria-label="Текущ PSK в Base64">
              <div class="channel-psk-actions">
                <button id="revealCurrentChannelPsk" type="button" class="ghost">
                  Покажи текущия PSK
                </button>
                <button id="copyCurrentChannelPsk" type="button" class="ghost" disabled>
                  Копирай Base64
                </button>
              </div>
              <p id="channelCurrentPskStatus" class="channel-psk-status">
                Скрит по подразбиране.
              </p>
            </div>`
          : ""
      }
      <p class="channel-secret-note wide">
        Името и PSK трябва да съвпадат при всички участници. Ключът не се записва
        в audit/history или browser storage. Clipboard-ът остава отговорност на оператора.
      </p>
    </div>
    <div class="channel-editor-actions">
      <button type="submit" class="primary">Запиши channel ${escapeHtml(slot.index)}</button>
    </div>`;
  initHelpTips(form);
  $("#channelPskMode").addEventListener("change", () => {
    configureChannelPskEditor({ reset: true });
  });
  $("#channelSimpleIndex").addEventListener("change", () =>
    configureChannelPskEditor({ reset: true }),
  );
  $("#channelPsk").addEventListener("input", updateNewChannelPskStatus);
  $("#channelPskConfirm").addEventListener("input", updateNewChannelPskStatus);
  $("#generateChannelPsk").addEventListener("click", () =>
    configureChannelPskEditor({ reset: true }),
  );
  $("#toggleChannelPsk").addEventListener("click", () => {
    const visible = $("#channelPsk").type === "text";
    $("#channelPsk").type = visible ? "password" : "text";
    $("#channelPskConfirm").type = visible ? "password" : "text";
    $("#toggleChannelPsk").textContent = visible ? "Покажи" : "Скрий";
  });
  $("#copyChannelPsk").addEventListener("click", () => {
    try {
      const base64 = bytesToBase64(parseChannelPsk($("#channelPsk").value));
      copyChannelSecret(base64, "PSK preview");
    } catch (error) {
      toast(error.message, true);
    }
  });
  if (slot.enabled) {
    $("#revealCurrentChannelPsk").addEventListener("click", () =>
      revealCurrentChannelPsk(slot),
    );
    $("#copyCurrentChannelPsk").addEventListener("click", () =>
      copyChannelSecret($("#channelCurrentPsk").value, "Текущият PSK"),
    );
  }
  configureChannelPskEditor({ reset: !slot.enabled });
}

function renderChannelSlots(slots) {
  state.channelSlots = slots;
  const list = $("#channelSlotList");
  if (!slots.length) {
    state.activeChannelSlot = null;
    list.className = "channel-slot-list empty-state";
    list.textContent =
      state.connection === "connected"
        ? "Радиото не върна channel slots."
        : "Свържи устройство, за да заредиш channel slots.";
    renderChannelEditor(null);
    return;
  }
  if (!slots.some((slot) => slot.index === state.activeChannelSlot && slot.editable)) {
    state.activeChannelSlot =
      slots.find((slot) => slot.enabled)?.index ??
      slots.find((slot) => slot.editable)?.index ??
      null;
  }
  list.className = "channel-slot-list";
  list.innerHTML = slots
    .map(
      (slot) => `
        <button type="button" class="channel-slot ${
          slot.index === state.activeChannelSlot ? "active" : ""
        }" data-channel-slot="${escapeHtml(slot.index)}" ${
          slot.editable ? "" : "disabled"
        }>
          <span class="channel-slot-index">${escapeHtml(slot.index)}</span>
          <span class="channel-slot-copy">
            <strong>${escapeHtml(slot.display_name)}</strong>
            <span>${escapeHtml(
              slot.enabled
                ? `${slot.role} · ${slot.psk_state}`
                : slot.editable
                  ? "Свободен · следващ за добавяне"
                  : "Свободен · добави предишния slot първо",
            )}</span>
          </span>
          <span class="channel-slot-state">${slot.enabled ? "ON" : "OFF"}</span>
        </button>`,
    )
    .join("");
  list.querySelectorAll(".channel-slot").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeChannelSlot = Number(button.dataset.channelSlot);
      renderChannelSlots(state.channelSlots);
    });
  });
  renderChannelEditor(
    slots.find((slot) => slot.index === state.activeChannelSlot) || null,
  );
}

async function refreshChannelSlots() {
  try {
    const { channels } = await api("/api/channel-slots");
    renderChannelSlots(channels);
  } catch (error) {
    toast(`Channel Manager: ${error.message}`, true);
  }
}

function channelPskPayload() {
  const mode = $("#channelPskMode").value;
  if (["unchanged", "default", "none"].includes(mode)) {
    return { psk_mode: mode, psk: "" };
  }
  if (mode === "simple") {
    return {
      psk_mode: "custom",
      psk: `simple${Number($("#channelSimpleIndex").value)}`,
    };
  }
  const bytes = parseChannelPsk($("#channelPsk").value);
  const allowedSizes = mode === "random128" ? [16] : mode === "random256" ? [32] : [1, 16, 32];
  if (!allowedSizes.includes(bytes.length)) {
    throw new Error(
      mode === "custom"
        ? "Custom PSK трябва да е 1, 16 или 32 bytes"
        : `Генерираният PSK трябва да е ${allowedSizes[0]} bytes`,
    );
  }
  if (mode === "custom") {
    const confirmation = parseChannelPsk($("#channelPskConfirm").value);
    if (
      bytes.length !== confirmation.length ||
      !bytes.every((value, index) => value === confirmation[index])
    ) {
      throw new Error("Custom PSK и потвърждението не съвпадат");
    }
  }
  return { psk_mode: "custom", psk: `base64:${bytesToBase64(bytes)}` };
}

async function saveChannel(event) {
  event.preventDefault();
  const slot = state.channelSlots.find(
    (item) => item.index === state.activeChannelSlot,
  );
  if (!slot) return;
  const role = $("#channelRole").value;
  const destructive = role === "DISABLED";
  let pskPayload = { psk_mode: "unchanged", psk: "" };
  if (!destructive) {
    try {
      pskPayload = channelPskPayload();
    } catch (error) {
      toast(error.message, true);
      return;
    }
  }
  const pskLabel = $("#channelPskMode").selectedOptions[0]?.textContent || "";
  const promptText = destructive
    ? `Да премахна channel ${slot.index} „${slot.display_name}“? Следващите Secondary slots могат да бъдат пренаредени от firmware-а.`
    : `Да запиша channel ${slot.index} с PSK режим „${pskLabel}“? Участниците с различно име/PSK няма да могат да го използват.`;
  if (!confirm(promptText)) return;
  try {
    await api(`/api/channel-slots/${slot.index}`, {
      method: "PUT",
      body: JSON.stringify({
        role,
        name: $("#channelName").value,
        ...pskPayload,
        uplink_enabled: $("#channelUplink").checked,
        downlink_enabled: $("#channelDownlink").checked,
        position_precision: Number($("#channelPositionPrecision").value || 0),
      }),
    });
    await Promise.all([refreshChannelSlots(), refreshChannels()]);
    toast(`Channel ${slot.index} е записан`);
  } catch (error) {
    toast(`Channel ${slot.index}: ${error.message}`, true);
  }
}

function roleAdvisorCard(role, guidance) {
  return `<article class="role-advisor-card ${guidance.className}">
    <div class="role-advisor-card-head">
      <h3>${escapeHtml(role)}</h3>
      <span class="role-badge">${escapeHtml(guidance.badge)}</span>
    </div>
    <p>${escapeHtml(guidance.summary)}</p>
    <div class="role-advisor-meta">
      <span>Подходящо</span><strong>${escapeHtml(guidance.use)}</strong>
      <span>Захранване</span><strong>${escapeHtml(guidance.power)}</strong>
      <span>Relay</span><strong>${escapeHtml(guidance.relay)}</strong>
      <span>Внимание</span><strong>${escapeHtml(guidance.caution)}</strong>
    </div>
  </article>`;
}

function renderRoleAdvisor() {
  $("#roleAdvisorCards").innerHTML = Object.entries(roleGuidance)
    .map(([role, guidance]) => roleAdvisorCard(role, guidance))
    .join("");
}

function openRoleAdvisor(trigger) {
  state.roleAdvisorTrigger = trigger || null;
  $("#roleAdvisorModal").classList.remove("hidden");
  setTimeout(() => $("#closeRoleAdvisor").focus(), 50);
}

function closeRoleAdvisor() {
  $("#roleAdvisorModal").classList.add("hidden");
  state.roleAdvisorTrigger?.focus();
  state.roleAdvisorTrigger = null;
}

function renderConfigGuidance(section) {
  const container = $("#configGuidance");
  if (!container || !section) return;
  if (section.name === "device") {
    const role = $("#config-role")?.value;
    const guidance = roleGuidance[role];
    if (!guidance) {
      container.className = "config-guidance";
      container.innerHTML = `
        <h4>Device role</h4>
        <p>Тази role стойност няма локално описание. Провери firmware документацията,
          преди да я приложиш.</p>`;
      return;
    }
    container.className = `config-guidance ${
      guidance.className === "infrastructure" ? "warning" : ""
    }`;
    container.innerHTML = `
      <h4>${escapeHtml(role)} · ${escapeHtml(guidance.badge)}</h4>
      <p>${escapeHtml(guidance.summary)}</p>
      <ul>
        <li><strong>Подходящо:</strong> ${escapeHtml(guidance.use)}</li>
        <li><strong>Внимание:</strong> ${escapeHtml(guidance.caution)}</li>
      </ul>
      <button id="openRoleAdvisor" type="button" class="ghost config-help-action">
        Сравни всички роли
      </button>`;
    return;
  }
  const guidance = configSectionGuidance[section.name];
  if (!guidance) {
    container.className = "config-guidance hidden";
    container.innerHTML = "";
    return;
  }
  container.className = `config-guidance ${guidance.warning ? "warning" : ""}`;
  container.innerHTML = `
    <h4>${escapeHtml(guidance.title)}</h4>
    <p>${escapeHtml(guidance.text)}</p>
    <ul>${guidance.bullets
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("")}</ul>`;
}

function fieldControl(sectionName, field) {
  const id = `config-${field.name}`;
  const label = `${escapeHtml(field.label)}${
    field.repeated ? " (comma-separated)" : ""
  } ${helpTrigger(
    configHelpFor(sectionName, field),
    `Помощ за ${sectionName}.${field.name}`,
  )}`;
  const common = `id="${id}" name="${field.name}" data-type="${field.type}" ${
    field.repeated ? 'data-repeated="true"' : ""
  } ${field.read_only ? "disabled" : ""}`;
  if (field.type === "bool") {
    return `<label class="config-toggle"><input type="checkbox" ${common} ${
      field.value ? "checked" : ""
    }><span>${label}</span></label>`;
  }
  if (field.type === "enum") {
    return `<label><span class="config-field-label">${label}</span><select ${common}>${field.enum_values
      .map(
        (value) =>
          `<option value="${escapeHtml(value)}" ${
            value === field.value ? "selected" : ""
          }>${escapeHtml(value)}</option>`,
      )
      .join("")}</select></label>`;
  }
  const inputType = field.secret ? "password" : field.type === "string" ? "text" : "number";
  const value = field.repeated
    ? (field.value || []).join(", ")
    : field.secret
      ? ""
      : field.value ?? "";
  const step = field.type === "float" ? 'step="any"' : "";
  const placeholder = field.secret ? 'placeholder="Остави празно, за да не се променя"' : "";
  return `<label><span class="config-field-label">${label}</span>
    <input type="${inputType}" ${common} value="${escapeHtml(value)}" ${step} ${placeholder}></label>`;
}

function selectConfigSection(name) {
  state.activeConfig = name;
  document.querySelectorAll(".config-section").forEach((button) => {
    button.classList.toggle("active", button.dataset.section === name);
  });
  const section = state.configSections.find((item) => item.name === name);
  const form = $("#configForm");
  if (!section) {
    form.className = "config-form empty-state";
    form.textContent = "Избери секция.";
    return;
  }
  const kindLabel =
    section.kind === "owner" ? "USER" : section.kind === "radio" ? "RADIO" : "MODULE";
  form.className = "config-form";
  form.innerHTML = `
    <div class="config-form-title">
      <div><span>${kindLabel}</span>
      <h3>${escapeHtml(section.label)}</h3></div>
      <button type="submit" class="primary">Запиши секцията</button>
    </div>
    <div id="configGuidance" class="config-guidance hidden"></div>
    <div class="config-fields">${section.fields
      .map((field) => fieldControl(section.name, field))
      .join("")}</div>`;
  renderConfigGuidance(section);
  initHelpTips(form);
  if (section.name === "device") {
    $("#config-role")?.addEventListener("change", () => renderConfigGuidance(section));
  }
}

function renderConfig(sections) {
  state.configSections = sections;
  const nav = $("#configSections");
  if (!sections.length) {
    nav.className = "config-sections empty-state";
    nav.textContent = $("#configTarget").value
      ? "Избери remote секция и натисни „Зареди секцията“."
      : "Няма заредена конфигурация.";
    $("#configForm").className = "config-form empty-state";
    $("#configForm").textContent = "Избери секция.";
    return;
  }
  nav.className = "config-sections";
  nav.innerHTML = sections
    .map(
      (section) =>
        `<button type="button" class="config-section" data-section="${escapeHtml(
          section.name,
        )}"><span>${
          section.kind === "owner" ? "U" : section.kind === "radio" ? "R" : "M"
        }</span>${escapeHtml(
          section.label,
        )}</button>`,
    )
    .join("");
  nav.querySelectorAll(".config-section").forEach((button) =>
    button.addEventListener("click", () => selectConfigSection(button.dataset.section)),
  );
  const selected = sections.some((section) => section.name === state.activeConfig)
    ? state.activeConfig
    : sections[0].name;
  selectConfigSection(selected);
}

async function refreshConfig() {
  try {
    const nodeId = $("#configTarget").value;
    const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
    const { sections } = await api(`/api/config${query}`);
    renderConfig(sections);
  } catch (error) {
    toast(error.message, true);
  }
}

async function saveConfig(event) {
  event.preventDefault();
  const section = state.configSections.find((item) => item.name === state.activeConfig);
  if (!section) return;
  if (
    !confirm(
      `Да запиша секция „${section.label}“ директно в радиото? Връзката може да се прекъсне.`,
    )
  ) {
    return;
  }
  const values = {};
  section.fields.forEach((field) => {
    if (field.read_only) return;
    const control = $(`#config-${field.name}`);
    let value;
    if (field.type === "bool") value = control.checked;
    else if (field.secret && control.value === "") value = "";
    else if (field.repeated) value = control.value;
    else if (field.type === "integer") value = Number.parseInt(control.value, 10);
    else if (field.type === "float") value = Number.parseFloat(control.value);
    else value = control.value;
    const original = field.repeated ? (field.value || []).join(", ") : field.value;
    const unchanged =
      field.secret && value === ""
        ? true
        : field.type === "bool"
          ? value === Boolean(original)
          : String(value) === String(original ?? "");
    if (!unchanged) values[field.name] = value;
  });
  if (!Object.keys(values).length) {
    toast("Няма променени стойности");
    return;
  }
  try {
    const data = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({
        section: section.name,
        values,
        node_id: $("#configTarget").value || null,
      }),
    });
    renderConfig(data.sections);
    toast(`Секция „${section.label}“ е записана`);
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadRemoteConfig() {
  const nodeId = $("#configTarget").value;
  if (!nodeId) return;
  const section = $("#remoteConfigSection").value;
  try {
    await api("/api/remote-admin/config", {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId, section }),
    });
    toast(`Remote admin заявката за „${section}“ е изпратена`);
  } catch (error) {
    toast(error.message, true);
  }
}

async function exportConfiguration() {
  const nodeId = $("#configTarget").value;
  const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
  try {
    const configDocument = await api(`/api/config/export${query}`);
    const blob = new Blob([JSON.stringify(configDocument, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `meshdesk-${configDocument.node_id || "radio"}-config.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    toast(error.message, true);
  }
}

async function importConfiguration(file) {
  if (!file) return;
  try {
    const documentData = JSON.parse(await file.text());
    const sections = Object.keys(documentData.sections || {});
    if (!sections.length) throw new Error("Файлът няма конфигурационни секции");
    if (
      !confirm(
        `Ще бъдат записани ${sections.length} секции директно в избраното радио. Да продължа ли?`,
      )
    ) {
      return;
    }
    const result = await api("/api/config/import", {
      method: "POST",
      body: JSON.stringify({
        document: documentData,
        node_id: $("#configTarget").value || null,
      }),
    });
    toast(`Импортирани секции: ${result.written.length}`);
    await refreshConfig();
  } catch (error) {
    toast(`Import грешка: ${error.message}`, true);
  } finally {
    $("#importConfigFile").value = "";
  }
}

async function refreshNodes() {
  try {
    const { nodes } = await api("/api/nodes");
    renderNodes(nodes);
    state.nodeRefreshAt = Date.now();
  } catch (error) {
    toast(error.message, true);
  }
}

async function syncRadioHistory() {
  const button = $("#syncHistory");
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = "Синхронизиране…";
  try {
    await api("/api/history/replay", {
      method: "POST",
      body: JSON.stringify({}),
    });
    toast("Заявката за пропуснати съобщения е изпратена към радиото");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.textContent = previous;
    button.disabled = state.connection !== "connected";
  }
}

async function runAdminAction(action) {
  const nodeId = $("#adminTarget").value || null;
  const targetName = $("#adminTarget").selectedOptions[0]?.textContent || "радиото";
  const confirmations = {
    reboot: `Да рестартирам ${targetName} след 10 секунди?`,
    shutdown: `Да изключа ${targetName} след 10 секунди?`,
    reset_nodedb: `Да изчистя NodeDB на ${targetName}?`,
  };
  if (confirmations[action] && !confirm(confirmations[action])) return;
  if (action === "factory_reset_config") {
    const typed = prompt(
      `Това ще нулира конфигурацията на ${targetName}. Въведи RESET CONFIG за потвърждение.`,
    );
    if (typed !== "RESET CONFIG") {
      if (typed !== null) toast("Нулирането е отказано: потвърждението не съвпада", true);
      return;
    }
  }
  if (action === "factory_reset_device") {
    const typed = prompt(
      `ПЪЛНО И НЕОБРАТИМО нулиране на ${targetName}. Въведи FULL RESET за потвърждение.`,
    );
    if (typed !== "FULL RESET") {
      if (typed !== null) toast("Пълното нулиране е отказано", true);
      return;
    }
  }
  const preserve =
    action === "reset_nodedb" &&
    !nodeId &&
    $("#preserveNodePreferences").checked;
  try {
    await api("/api/administration", {
      method: "POST",
      body: JSON.stringify({
        action,
        node_id: nodeId,
        preserve_node_preferences: preserve,
      }),
    });
    toast(`${operationLabel({ operation: "administration", admin_action: action })} е изпратено`);
  } catch (error) {
    toast(error.message, true);
  }
}

async function sendMessage(event) {
  event.preventDefault();
  const text = $("#messageText").value.trim();
  if (!text) return;
  const key = state.selectedConversation;
  if (!key) {
    toast("Първо избери разговор", true);
    return;
  }
  const direct = key.startsWith("direct:");
  const destination = direct ? key.slice("direct:".length) : "^all";
  const channel = direct
    ? Number($("#channel").value)
    : Number(key.slice("channel:".length));
  const selectedNode = state.nodes.find((node) => node.id === destination);
  if (selectedNode && !selectedNode.is_messageable) {
    toast("Този възел е маркиран като неспособен да приема лични съобщения", true);
    return;
  }
  try {
    await api("/api/messages", {
      method: "POST",
      body: JSON.stringify({
        text,
        destination,
        channel,
        want_ack: $("#wantAck").checked,
      }),
    });
    $("#messageText").value = "";
    updateByteCount();
  } catch (error) {
    toast(error.message, true);
  }
}

function eventTitle(event) {
  if (event.kind === "outgoing") return `Към ${event.to}`;
  if (event.kind === "message_status")
    return event.status === "sent"
      ? "Предадено на радиото"
      : "Предадено на радиото · чака ACK";
  if (event.kind === "incoming") return `От ${event.from || "unknown"}`;
  if (event.kind === "delivery")
    return event.status === "delivered"
      ? "Доставено / ACK"
      : event.status === "timeout"
        ? "Изтече ACK timeout"
        : "Недоставено / NAK";
  if (event.kind === "operation_request") return `${operationLabel(event)} · заявка`;
  if (event.kind === "operation_result")
    return `${operationLabel(event)} · ${event.success ? "отговор" : "грешка"}`;
  if (event.kind === "config") return "Конфигурация";
  if (event.kind === "store_forward") return "Store & Forward история";
  if (event.kind === "error") return "Грешка";
  return "Състояние";
}

function renderUnread() {
  const total = Object.values(state.unread).reduce((sum, count) => sum + count, 0);
  document.title = total ? `(${total}) MeshDesk` : "MeshDesk";
  renderConversations();
  if (state.selectedConversation) {
    $("#markConversationRead").disabled = !(state.unread[state.selectedConversation] > 0);
  }
}

function markMessagesRead() {
  state.unread = {};
  state.readThrough = state.lastEvent;
  localStorage.setItem("meshdeskReadThrough", String(state.readThrough));
  renderUnread();
}

function addChatEvent(event) {
  if ((event.kind === "incoming" || event.kind === "outgoing") && event.text) {
    const key =
      event.kind === "incoming"
        ? event.conversation ||
          (event.is_direct ? `direct:${event.from}` : `channel:${event.channel ?? 0}`)
        : event.to && event.to !== "^all"
          ? `direct:${event.to}`
          : `channel:${event.channel ?? 0}`;
    if (!key) return;
    state.closedConversations.delete(key);
    const messages = (state.chatMessages[key] ||= []);
    const eventId =
      event.event_id || `${event.profile_id || "legacy"}:${event.seq}:${event.time}`;
    if (!messages.some((message) => message.eventId === eventId)) {
      const packetId = event.packet?.id;
      const earlyReceipt =
        packetId != null ? state.deliveryReceipts[String(packetId)] : null;
      messages.push({
        eventId,
        seq: event.seq,
        time: event.time,
        text: event.text,
        from: event.from,
        direction: event.kind,
        packetId,
        sourceEvent: event,
        wantAck: event.want_ack !== false,
        delivery:
          event.delivery ||
          (event.want_ack === false
            ? "sent"
            : earlyReceipt?.status === "delivered"
              ? "delivered"
              : earlyReceipt
                ? earlyReceipt.status
                : "enroute"),
        clientId: event.client_id,
      });
      if (earlyReceipt) delete state.deliveryReceipts[String(packetId)];
    }
    return;
  }
  if (event.kind === "message_status") {
    const matched = Object.values(state.chatMessages).some((messages) => {
      const message = messages.find(
        (item) =>
          item.direction === "outgoing" &&
          ((event.client_id && item.clientId === event.client_id) ||
            (event.packet_id != null &&
              item.packetId != null &&
              String(item.packetId) === String(event.packet_id))),
      );
      if (!message) return false;
      message.delivery = event.status;
      message.packetId = event.packet_id ?? message.packetId;
      message.statusEvent = event;
      if (event.packet && Object.keys(event.packet).length) {
        message.sourceEvent.packet = event.packet;
      }
      return true;
    });
    if (!matched && event.client_id) {
      state.deliveryReceipts[`client:${event.client_id}`] = event;
    }
    return;
  }
  if (event.kind === "delivery") {
    const matched = Object.values(state.chatMessages).some((messages) => {
      const message = messages.find(
        (item) =>
          item.direction === "outgoing" &&
          ((event.client_id && item.clientId === event.client_id) ||
            (item.packetId != null &&
              event.packet_id != null &&
              String(item.packetId) === String(event.packet_id))),
      );
      if (!message) return false;
      message.delivery = event.status;
      message.deliveryError = event.error;
      message.deliveryEvent = event;
      return true;
    });
    if (!matched) {
      if (event.client_id) {
        state.deliveryReceipts[`client:${event.client_id}`] = event;
      } else if (event.packet_id != null) {
        state.deliveryReceipts[String(event.packet_id)] = event;
      }
    }
  }
}

function appendEvents(events, { historical = false } = {}) {
  if (!historical) {
    events = events.filter(
      (event) =>
        !event.profile_id ||
        (state.profileId && event.profile_id === state.profileId),
    );
  }
  if (!events.length) return;
  const container = $("#events");
  if (container.classList.contains("empty-state")) {
    container.className = "events";
    container.innerHTML = "";
  }
  events.forEach((event) => {
    state.eventLog.push(event);
    if (state.eventLog.length > 500) state.eventLog.shift();
    addChatEvent(event);
    const row = document.createElement("article");
    row.className = `event ${event.kind}`;
    const body =
      event.text ||
      event.message ||
      (["operation_request", "operation_result"].includes(event.kind)
        ? `${operationLabel(event)} · ${event.target}${
            event.error ? ` · ${event.error}` : ""
          }`
        : event.kind === "store_forward"
        ? `Върнати ${event.history_messages ?? 0} съобщения · marker ${
            event.last_request ?? "—"
          }`
        : event.kind === "delivery"
        ? event.error === "NONE"
          ? `Packet ${event.packet_id || ""} acknowledged by ${event.to}`
          : `${event.error || "NO_RESPONSE"} · packet ${event.packet_id || ""}`
        : event.kind === "message_status"
        ? `Packet ${event.packet_id || "—"} · ${
            event.status === "sent" ? "без заявен ACK" : "изчаква ACK"
          }`
        : `${event.portnum || "Meshtastic packet"} · channel ${event.channel ?? 0}`);
    row.innerHTML = `
      <span class="event-dot"></span>
      <div><strong>${escapeHtml(eventTitle(event))}</strong><p>${escapeHtml(body)}</p></div>
      <time>${new Date(event.time).toLocaleTimeString()}</time>`;
    container.prepend(row);
    if (!historical) state.lastEvent = Math.max(state.lastEvent, event.seq);
    if (
      !historical &&
      event.kind === "incoming" &&
      event.text &&
      event.seq > state.readThrough &&
      event.conversation &&
      (event.conversation !== state.selectedConversation || document.hidden)
    ) {
      state.unread[event.conversation] = (state.unread[event.conversation] || 0) + 1;
    }
  });
  renderUnread();
  renderChat();
  if (!historical && events.some((event) => event.kind === "operation_result")) {
    setTimeout(refreshNodes, 250);
  }
  if (
    !historical &&
    events.some(
      (event) =>
        event.kind === "operation_result" &&
        event.operation === "remote_config" &&
        event.success &&
        event.target === $("#configTarget").value.toLowerCase(),
    )
  ) {
    setTimeout(refreshConfig, 250);
  }
  if (state.inspector) renderInspector();
  while (container.children.length > 100) container.lastElementChild.remove();
}

async function pollEvents() {
  try {
    const { events } = await api(`/api/events?after=${state.lastEvent}`);
    appendEvents(events);
  } catch {
    // A later poll will recover after a brief backend restart.
  }
}

function updateByteCount() {
  const size = new TextEncoder().encode($("#messageText").value).length;
  const counter = $("#byteCount");
  counter.textContent = `${size} / 230 bytes`;
  counter.classList.toggle("over", size > 230);
  $("#sendButton").disabled =
    state.connection !== "connected" ||
    !state.selectedConversation ||
    size === 0 ||
    size > 230;
}

function openDirectModal() {
  fillDirectRecipients();
  $("#directModal").classList.remove("hidden");
  if ($("#directRecipient").options.length > 1) {
    $("#directRecipient").selectedIndex = 1;
    $("#directManualLabel").classList.add("hidden");
    $("#directRecipient").focus();
  } else {
    $("#directRecipient").value = "__manual";
    $("#directManualLabel").classList.remove("hidden");
    $("#directManual").focus();
  }
}

function closeDirectModal() {
  $("#directModal").classList.add("hidden");
}

function createDirectConversation() {
  const selected = $("#directRecipient").value;
  const nodeId =
    selected === "__manual" ? $("#directManual").value.trim() : selected;
  if (!/^![0-9a-fA-F]{8}$/.test(nodeId)) {
    toast("Node ID трябва да е във формат !1234abcd", true);
    $("#directManual").focus();
    return;
  }
  const node = nodeForId(nodeId);
  if (node && !node.is_messageable) {
    toast("Този възел не може да приема лични съобщения", true);
    return;
  }
  state.chatMessages[`direct:${nodeId}`] ||= [];
  selectConversation(`direct:${nodeId}`);
  closeDirectModal();
  $("#messageText").focus();
}

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    setTransport(tab.dataset.transport);
    markConnectionProfileDirty();
  }),
);
$("#connectForm").addEventListener("submit", connect);
$("#disconnectButton").addEventListener("click", disconnect);
$("#connectionToggle").addEventListener("click", () => {
  state.connectionExpanded = !state.connectionExpanded;
  if (state.status) updateControls(state.status);
});
$("#connectionProfile").addEventListener("change", applyConnectionProfile);
$("#saveConnectionProfile").addEventListener("click", openConnectionProfileModal);
$("#deleteConnectionProfile").addEventListener("click", deleteConnectionProfile);
$("#rebindConnectionProfile").addEventListener("click", rebindConnectionProfile);
$("#cancelConnectionProfile").addEventListener("click", closeConnectionProfileModal);
$("#confirmConnectionProfile").addEventListener("click", saveConnectionProfile);
$("#connectionProfileName").addEventListener("keydown", (event) => {
  if (event.key === "Enter") saveConnectionProfile();
});
$("#connectionProfileModal").addEventListener("click", (event) => {
  if (event.target === $("#connectionProfileModal")) closeConnectionProfileModal();
});
$("#discoverTcpButton").addEventListener("click", discoverTcpDevices);
$("#useDiscoveredTcp").addEventListener("click", useDiscoveredTcpDevice);
$("#tcpDiscoveredDevice").addEventListener("change", renderTcpDiscoveryDetails);
["#tcpHost", "#tcpPort", "#bleDevice"].forEach((selector) => {
  $(selector).addEventListener("input", markConnectionProfileDirty);
  $(selector).addEventListener("change", markConnectionProfileDirty);
});
$("#scanButton").addEventListener("click", scanBle);
$("#pairButton").addEventListener("click", startPairing);
$("#submitPin").addEventListener("click", submitPairingPin);
$("#cancelPairing").addEventListener("click", cancelPairing);
$("#pairingPin").addEventListener("keydown", (event) => {
  if (event.key === "Enter") submitPairingPin();
});
$("#messageForm").addEventListener("submit", sendMessage);
$("#channel").addEventListener("change", () => {
  if (state.selectedConversation?.startsWith("channel:")) {
    selectConversation(`channel:${$("#channel").value}`);
  }
});
$("#syncHistory").addEventListener("click", syncRadioHistory);
$("#messageText").addEventListener("input", updateByteCount);
$("#messageText").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!$("#sendButton").disabled) $("#messageForm").requestSubmit();
  }
});
$("#conversationSearch").addEventListener("input", renderConversations);
$("#newDirectButton").addEventListener("click", openDirectModal);
$("#closeConversation").addEventListener("click", closeConversation);
$("#cancelDirect").addEventListener("click", closeDirectModal);
$("#openDirect").addEventListener("click", createDirectConversation);
$("#directRecipient").addEventListener("change", () => {
  const manual = $("#directRecipient").value === "__manual";
  $("#directManualLabel").classList.toggle("hidden", !manual);
  if (manual) $("#directManual").focus();
});
$("#directManual").addEventListener("keydown", (event) => {
  if (event.key === "Enter") createDirectConversation();
});
$("#directModal").addEventListener("click", (event) => {
  if (event.target === $("#directModal")) closeDirectModal();
});
$("#nodeSearch").addEventListener("input", () => renderNodes(state.nodes));
$("#nodeTransportFilter").addEventListener("change", () => renderNodes(state.nodes));
$("#nodePreferenceFilter").addEventListener("change", () => renderNodes(state.nodes));
$("#showSelfNode").addEventListener("change", () => renderNodes(state.nodes));
$("#nodeSort").addEventListener("change", () => renderNodes(state.nodes));
$("#refreshNodes").addEventListener("click", refreshNodes);
$("#settingsConfigTab").addEventListener("click", () => selectSettingsView("config"));
$("#settingsChannelsTab").addEventListener("click", () => selectSettingsView("channels"));
document.querySelector(".settings-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const channels =
    event.key === "ArrowRight" || event.key === "End"
      ? true
      : event.key === "ArrowLeft" || event.key === "Home"
        ? false
        : $("#settingsChannelsTab").getAttribute("aria-selected") !== "true";
  selectSettingsView(channels ? "channels" : "config");
  $(channels ? "#settingsChannelsTab" : "#settingsConfigTab").focus();
});
$("#configPanel").addEventListener("toggle", () => {
  if (!$("#configPanel").open) clearCurrentChannelPskReveal();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearCurrentChannelPskReveal();
    const newPsk = $("#channelPsk");
    const confirmation = $("#channelPskConfirm");
    if (newPsk) newPsk.type = "password";
    if (confirmation) confirmation.type = "password";
    const toggle = $("#toggleChannelPsk");
    if (toggle) toggle.textContent = "Покажи";
  }
});
$("#reloadChannels").addEventListener("click", () =>
  Promise.all([refreshChannelSlots(), refreshChannels()]),
);
$("#channelEditor").addEventListener("submit", saveChannel);
$("#reloadConfig").addEventListener("click", refreshConfig);
$("#configTarget").addEventListener("change", async () => {
  state.activeConfig = null;
  const remote = Boolean($("#configTarget").value);
  $("#remoteConfigControls").classList.toggle("hidden", !remote);
  await refreshConfig();
});
$("#adminTarget").addEventListener("change", updateAdminTarget);
document.querySelectorAll(".admin-action").forEach((button) => {
  button.addEventListener("click", () => runAdminAction(button.dataset.adminAction));
});
$("#loadRemoteConfig").addEventListener("click", loadRemoteConfig);
$("#exportConfig").addEventListener("click", exportConfiguration);
$("#importConfig").addEventListener("click", () => $("#importConfigFile").click());
$("#importConfigFile").addEventListener("change", () =>
  importConfiguration($("#importConfigFile").files[0]),
);
$("#copyPublicKey").addEventListener("click", async () => {
  const key = $("#localPublicKey").textContent;
  if (!key || key === "—") return;
  try {
    await navigator.clipboard.writeText(key);
    toast("Публичният ключ е копиран");
  } catch {
    toast("Браузърът не позволи копиране в clipboard", true);
  }
});
$("#configForm").addEventListener("submit", saveConfig);
$("#configForm").addEventListener("click", (event) => {
  const trigger = event.target.closest("#openRoleAdvisor");
  if (trigger) openRoleAdvisor(trigger);
});
$("#closeRoleAdvisor").addEventListener("click", closeRoleAdvisor);
$("#roleAdvisorModal").addEventListener("click", (event) => {
  if (event.target === $("#roleAdvisorModal")) closeRoleAdvisor();
});
$("#markRead").addEventListener("click", markMessagesRead);
$("#markConversationRead").addEventListener("click", () => {
  if (!state.selectedConversation) return;
  state.unread[state.selectedConversation] = 0;
  renderUnread();
});
$("#clearEvents").addEventListener("click", () => {
  $("#events").className = "events empty-state";
  $("#events").textContent = "Списъкът е изчистен.";
});
$("#closeInspector").addEventListener("click", closeInspector);
$("#inspectorBackdrop").addEventListener("click", closeInspector);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideHelpTooltip();
  if (event.key === "Escape" && !$("#roleAdvisorModal").classList.contains("hidden")) {
    closeRoleAdvisor();
    return;
  }
  if (
    event.key === "Escape" &&
    !$("#connectionProfileModal").classList.contains("hidden")
  ) {
    closeConnectionProfileModal();
    return;
  }
  if (event.key === "Escape" && state.inspector) closeInspector();
});

organizeWorkspace();
initHelpTips();
refreshConnectionProfiles();
refreshStatus();
pollEvents();
renderRoleAdvisor();
renderConversations();
renderChat();
setInterval(refreshStatus, 1500);
setInterval(pollEvents, 1000);
setInterval(pollPairing, 1000);
setInterval(applyRequestCooldowns, 1000);
setInterval(() => {
  if (state.connection === "connected" && Date.now() - state.nodeRefreshAt > 30000) {
    refreshNodes();
  }
}, 5000);
