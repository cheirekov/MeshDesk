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
  unread: {},
  chatMessages: {},
  deliveryReceipts: {},
  selectedConversation: null,
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
  $("#channel").disabled =
    !connected || Boolean(state.selectedConversation?.startsWith("channel:"));
  $("#wantAck").disabled = !connected;
  $("#sendButton").disabled = !connected;
  $("#newDirectButton").disabled = !connected;
  $("#refreshNodes").disabled = !connected;
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
  updateByteCount();
  if (status.error && status.error !== state.lastError) toast(status.error, true);
  state.lastError = status.error;
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
    if ((status.profile_id || null) !== state.profileId) {
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
    updateControls(status);
    if (!wasConnected && status.state === "connected") {
      toast(`Свързано: ${status.target}`);
      await verifySelectedConnectionProfile(status);
      await Promise.all([refreshNodes(), refreshChannels(), refreshConfig()]);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function activateProfile(profileId, eventSequence) {
  state.profileId = profileId;
  state.lastEvent = eventSequence || 0;
  state.chatMessages = {};
  state.deliveryReceipts = {};
  state.eventLog = [];
  state.unread = {};
  state.selectedConversation = null;
  state.nodes = [];
  state.channels = [];
  state.readThrough = 0;
  $("#events").className = "events empty-state";
  $("#events").textContent = "Все още няма събития.";
  renderNodes([]);
  renderChannels([]);
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
    updateControls(await api("/api/disconnect", { method: "POST" }));
    renderNodes([]);
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
  return [...new Set([...channelKeys, ...dynamicKeys])].sort((left, right) => {
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
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
  if (!message.wantAck) return "";
  if (message.delivery === "delivered") return '<span class="delivery delivered">✓ ACK</span>';
  if (message.delivery === "failed") return '<span class="delivery failed">× NAK</span>';
  return '<span class="delivery pending">… чака ACK</span>';
}

function renderChat() {
  if (!state.selectedConversation && conversationKeys().length) {
    state.selectedConversation = conversationKeys()[0];
  }
  const key = state.selectedConversation;
  const meta = conversationMeta(key);
  $("#chatAvatar").textContent = meta.avatar;
  $("#chatTitle").textContent = meta.title;
  $("#chatSubtitle").textContent = meta.subtitle;

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
  $("#channel").disabled = !connected || meta.type === "channel";
  $("#messageText").disabled = !connected || !key;
  $("#messageText").placeholder = key
    ? `Съобщение до ${meta.title}…`
    : "Избери разговор…";
  $("#markConversationRead").disabled = !key || !(state.unread[key] > 0);
  updateByteCount();
}

function selectConversation(key) {
  state.selectedConversation = key;
  state.unread[key] = 0;
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
  const staleBefore = Date.now() / 1000 - 24 * 60 * 60;
  const filtered = nodes.filter((node) => {
    const matchesQuery =
      !query ||
      [node.long_name, node.short_name, node.id, node.hardware, node.role]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase("bg").includes(query));
    if (!matchesQuery) return false;
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
  filtered.sort(sorters[$("#nodeSort").value] || sorters.recent);

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
            <button type="button"
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
              aria-label="${node.is_ignored ? "Спри игнорирането" : "Игнорирай възела"}">⊘</button>
            <button type="button" class="node-message ghost" data-node="${escapeHtml(
              node.id,
            )}" ${node.is_messageable ? "" : "disabled"}>Съобщение</button>
            <button type="button" class="node-quick-action ghost" data-action="traceroute"
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
    button.addEventListener("click", () =>
      requestNodeAction(button.dataset.node, button.dataset.action),
    );
  });
  container.querySelectorAll(".node-preference").forEach((button) => {
    button.addEventListener("click", () =>
      requestNodeAction(button.dataset.node, button.dataset.action),
    );
  });
  container.querySelectorAll(".node-inspect").forEach((button) => {
    button.addEventListener("click", () => openNodeInspector(button.dataset.node));
  });
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
  } else {
    body = "<p>Node database е обновена.</p>";
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
  state.inspector = { type: "node", nodeId };
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
  const managedNodeOptions = [
    `<option value="">Локално: ${escapeHtml(
      state.status?.profile_name || state.profileId || "радио",
    )}</option>`,
    ...state.nodes.map(
      (candidate) =>
        `<option value="${escapeHtml(candidate.id)}">Remote: ${escapeHtml(
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
          data-action="traceroute">Traceroute</button>
        <div class="telemetry-request">
          <select id="inspectorTelemetryType">
            <option value="device">Device metrics</option>
            <option value="environment">Environment</option>
            <option value="air_quality">Air quality</option>
            <option value="power">Power</option>
            <option value="local_stats">Local stats</option>
          </select>
          <button type="button" class="secondary inspector-action"
            data-action="telemetry">Telemetry</button>
        </div>
        <button type="button" class="secondary inspector-action"
          data-action="position">Position</button>
        <button type="button" class="ghost inspector-message"
          ${node.is_messageable ? "" : "disabled"}>Съобщение</button>
        <button type="button" class="ghost inspector-admin">Remote admin</button>
      </div>
    </section>

    <section class="inspector-section">
      <div class="inspector-section-title"><h3>Node database</h3></div>
      <label class="inspector-admin-target">
        Промени NodeDB на
        <select id="inspectorNodeDbTarget">${managedNodeOptions}</select>
      </label>
      <div class="inspector-actions">
        <button type="button" class="ghost inspector-action"
          data-action="${node.is_favorite ? "unfavorite" : "favorite"}">${
            node.is_favorite ? "Премахни от любими" : "Добави в любими"
          }</button>
        <button type="button" class="ghost inspector-action"
          data-action="${node.is_ignored ? "unignore" : "ignore"}">${
            node.is_ignored ? "Спри игнорирането" : "Игнорирай възела"
          }</button>
      </div>
      <p class="inspector-note">При Remote избор заявката минава през PKI admin.
        Игнорирането може да спре обработката на пакети от този възел от избраното радио.</p>
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

  $("#inspectorContent").querySelectorAll(".inspector-action").forEach((button) => {
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
  if (
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
      `${operationLabel({ operation: action, telemetry_type: telemetryType })} ${
        managedNodeId ? "е изпратено към remote NodeDB" : "е приложено"
      }`,
    );
  } catch (error) {
    toast(error.message, true);
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

function fieldControl(field) {
  const id = `config-${field.name}`;
  const common = `id="${id}" name="${field.name}" data-type="${field.type}" ${
    field.repeated ? 'data-repeated="true"' : ""
  } ${field.read_only ? "disabled" : ""}`;
  if (field.type === "bool") {
    return `<label class="config-toggle"><input type="checkbox" ${common} ${
      field.value ? "checked" : ""
    }><span>${escapeHtml(field.label)}</span></label>`;
  }
  if (field.type === "enum") {
    return `<label>${escapeHtml(field.label)}<select ${common}>${field.enum_values
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
  return `<label>${escapeHtml(field.label)}${
    field.repeated ? " (comma-separated)" : ""
  }<input type="${inputType}" ${common} value="${escapeHtml(value)}" ${step} ${placeholder}></label>`;
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
    <div class="config-fields">${section.fields.map(fieldControl).join("")}</div>`;
  renderConfigGuidance(section);
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
  if (event.kind === "incoming") return `От ${event.from || "unknown"}`;
  if (event.kind === "delivery")
    return event.status === "delivered" ? "Доставено / ACK" : "Недоставено / NAK";
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
          event.want_ack === false
            ? null
            : earlyReceipt?.status === "delivered"
              ? "delivered"
              : earlyReceipt
                ? "failed"
                : "pending",
      });
      if (earlyReceipt) delete state.deliveryReceipts[String(packetId)];
    }
    return;
  }
  if (event.kind === "delivery") {
    const matched = Object.values(state.chatMessages).some((messages) => {
      const message = messages.find(
        (item) =>
          item.direction === "outgoing" &&
          item.packetId != null &&
          String(item.packetId) === String(event.packet_id),
      );
      if (!message) return false;
      message.delivery = event.status === "delivered" ? "delivered" : "failed";
      message.deliveryError = event.error;
      message.deliveryEvent = event;
      return true;
    });
    if (!matched && event.packet_id != null) {
      state.deliveryReceipts[String(event.packet_id)] = event;
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
$("#nodeSort").addEventListener("change", () => renderNodes(state.nodes));
$("#refreshNodes").addEventListener("click", refreshNodes);
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
refreshConnectionProfiles();
refreshStatus();
pollEvents();
renderRoleAdvisor();
renderConversations();
renderChat();
setInterval(refreshStatus, 1500);
setInterval(pollEvents, 1000);
setInterval(pollPairing, 1000);
setInterval(() => {
  if (state.connection === "connected" && Date.now() - state.nodeRefreshAt > 30000) {
    refreshNodes();
  }
}, 5000);
