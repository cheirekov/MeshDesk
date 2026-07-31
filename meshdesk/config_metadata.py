from __future__ import annotations

from typing import Any

_INTEGER_DOMAINS = {
    3: "−9 223 372 036 854 775 808 … 9 223 372 036 854 775 807",  # int64
    4: "0 … 18 446 744 073 709 551 615",  # uint64
    5: "−2 147 483 648 … 2 147 483 647",  # int32
    6: "0 … 18 446 744 073 709 551 615",  # fixed64
    7: "0 … 4 294 967 295",  # fixed32
    13: "0 … 4 294 967 295",  # uint32
    15: "−2 147 483 648 … 2 147 483 647",  # sfixed32
    16: "−9 223 372 036 854 775 808 … 9 223 372 036 854 775 807",  # sfixed64
    17: "−2 147 483 648 … 2 147 483 647",  # sint32
    18: "−9 223 372 036 854 775 808 … 9 223 372 036 854 775 807",  # sint64
}

_TYPE_NAMES = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "boolean",
    9: "UTF-8 text",
    12: "bytes",
    13: "uint32",
    14: "enum",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}


# Curated operator-facing metadata. Protobuf scalar defaults alone are often
# misleading because Meshtastic firmware interprets zero as a role-aware or
# hardware-aware default. Keep only values that are stable and backed by the
# current protobuf/firmware behavior.
CONFIG_FIELD_METADATA: dict[tuple[str, str], dict[str, Any]] = {
    ("network", "enabled_protocols"): {
        "label": "Допълнително IP излъчване",
        "default": "0 · NO_BROADCAST",
        "minimum": 0,
        "maximum": 1,
        "recommended": "0, освен ако умишлено използваш UDP discovery/broadcast в доверена LAN",
        "choices": [
            {
                "value": 0,
                "label": "0 · Без auxiliary broadcast (NO_BROADCAST)",
            },
            {
                "value": 1,
                "label": "1 · UDP broadcast в локалната IP мрежа",
            },
        ],
        "note": "Това поле не включва/изключва Meshtastic TCP API на порт 4403.",
    },
    ("neighbor_info", "update_interval"): {
        "default": "21600 s · 6 часа",
        "minimum": 14400,
        "maximum": 2147483647,
        "unit": "s",
        "recommended": "21600 s (6 часа); 14400 s е абсолютният firmware минимум",
        "note": "По-ниска стойност се заменя от firmware с 21600 s.",
        "enforce_range": True,
    },
    ("device", "node_info_broadcast_secs"): {
        "default": "10800 s · 3 часа",
        "minimum": 3600,
        "maximum": 2147483647,
        "unit": "s",
        "recommended": "10800 s; не намалявай под 3600 s",
    },
    ("lora", "hop_limit"): {
        "default": "0 означава firmware default 3",
        "minimum": 0,
        "maximum": 7,
        "recommended": "3 за повечето мрежи",
        "enforce_range": True,
    },
    ("lora", "tx_power"): {
        "default": "0 · region/hardware default",
        "unit": "dBm",
        "recommended": "Остави 0 или стойност в законовия и хардуерния лимит за избрания region",
        "note": "Допустимият максимум зависи от region и radio chip; няма един универсален range.",
    },
    ("position", "gps_update_interval"): {
        "default": "120 s за обикновен node; 86400 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "120 s за portable CLIENT; по-дълго при стационарен или power-saving node",
    },
    ("position", "position_broadcast_secs"): {
        "default": "3600 s за обикновен node; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече; default channel може да наложи role-aware minimum",
    },
    ("position", "broadcast_smart_minimum_interval_secs"): {
        "default": "300 s",
        "unit": "s",
        "recommended": "300 s или повече на default channel",
    },
    ("position", "broadcast_smart_minimum_distance"): {
        "unit": "m",
        "recommended": "Съобрази с точността на GPS; твърде ниско увеличава position traffic",
    },
    ("display", "screen_on_secs"): {
        "default": "600 s за обикновен node; 1 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "30–600 s според захранването и нуждата от локален дисплей",
    },
    ("power", "wait_bluetooth_secs"): {
        "default": "60 s за обикновен node; 1 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "60 s за лесно BLE свързване; по-кратко за power-saving",
    },
    ("telemetry", "device_update_interval"): {
        "default": "3600 s; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече; на default channel минимумът обикновено е 1800 s",
    },
    ("telemetry", "environment_update_interval"): {
        "default": "3600 s; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече, освен при измерена нужда от по-чести данни",
    },
    ("telemetry", "air_quality_interval"): {
        "default": "3600 s; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече",
    },
    ("telemetry", "power_update_interval"): {
        "default": "3600 s; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече",
    },
    ("telemetry", "health_update_interval"): {
        "default": "3600 s; 43200 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "3600 s или повече",
    },
    ("paxcounter", "wifi_threshold"): {
        "default": "-80 dBm",
        "unit": "dBm",
        "recommended": "-80 dBm като начална стойност",
    },
    ("paxcounter", "ble_threshold"): {
        "default": "-80 dBm",
        "unit": "dBm",
        "recommended": "-80 dBm като начална стойност",
    },
    ("owner", "long_name"): {
        "protocol_type": "UTF-8 text",
        "default": "името, генерирано от firmware",
        "domain": "текст; използвай кратко и разпознаваемо име",
        "recommended": "описателно име без чувствителни лични данни",
    },
    ("owner", "short_name"): {
        "protocol_type": "UTF-8 text",
        "default": "4-знаковото име, генерирано от firmware",
        "domain": "до 4 Unicode знака",
        "recommended": "уникални 4 знака, които се четат добре в тесен UI",
    },
    ("owner", "is_licensed"): {
        "protocol_type": "boolean",
        "default": "false",
        "domain": "false / true",
        "recommended": "true само при валиден радиолюбителски лиценз и подходяща конфигурация",
    },
    ("owner", "is_unmessagable"): {
        "protocol_type": "boolean",
        "default": "false",
        "domain": "false / true",
        "recommended": "false за нормален client; true за възел, който не трябва да приема DM",
    },
}


def _display_default(descriptor: Any) -> str:
    if descriptor.is_repeated:
        return "празен списък"
    value = descriptor.default_value
    if descriptor.enum_type is not None:
        item = descriptor.enum_type.values_by_number.get(int(value))
        return item.name if item is not None else str(value)
    if descriptor.type == descriptor.TYPE_BOOL:
        return "true" if value else "false"
    if descriptor.type == descriptor.TYPE_STRING:
        return "празен текст" if value == "" else str(value)
    if descriptor.type == descriptor.TYPE_BYTES:
        return "празна byte стойност"
    return str(value)


def _descriptor_metadata(descriptor: Any) -> dict[str, Any]:
    field_type = descriptor.type
    metadata: dict[str, Any] = {
        "protocol_type": _TYPE_NAMES.get(field_type, "protobuf scalar"),
        "protocol_default": _display_default(descriptor),
    }
    if descriptor.is_repeated:
        metadata["domain"] = "списък; конкретният firmware може да ограничава броя записи"
        metadata["recommended"] = "Запази текущия списък, ако не променяш съзнателно тази функция."
    elif descriptor.enum_type is not None:
        metadata["domain"] = " / ".join(item.name for item in descriptor.enum_type.values)
        metadata["recommended"] = "Запази текущия режим, освен ако Help описанието изисква друг."
    elif field_type == descriptor.TYPE_BOOL:
        metadata["domain"] = "false / true"
        metadata["recommended"] = (
            "Запази текущото състояние, ако функцията не ти е необходима изрично."
        )
    elif field_type in _INTEGER_DOMAINS:
        metadata["domain"] = f"типов диапазон {_INTEGER_DOMAINS[field_type]}"
        metadata["recommended"] = (
            "Запази текущата стойност; типовият диапазон не е гарантиран firmware лимит."
        )
    elif field_type in {descriptor.TYPE_FLOAT, descriptor.TYPE_DOUBLE}:
        metadata["domain"] = "крайно десетично число; firmware може да налага по-тесни граници"
        metadata["recommended"] = (
            "Запази текущата стойност, освен при измерена хардуерна или RF нужда."
        )
    elif field_type == descriptor.TYPE_STRING:
        metadata["domain"] = "UTF-8 текст; дължината може да е ограничена от firmware"
        metadata["recommended"] = (
            "Използвай кратка стойност и запази текущата, ако функцията не се променя."
        )
    elif field_type == descriptor.TYPE_BYTES:
        metadata["domain"] = "binary стойност"
        metadata["recommended"] = "Не променяй без специализиран key/identity workflow."
    return metadata


def config_field_metadata(
    section: str,
    field: str,
    descriptor: Any | None = None,
) -> dict[str, Any]:
    metadata = _descriptor_metadata(descriptor) if descriptor is not None else {}
    metadata.update(CONFIG_FIELD_METADATA.get((section, field), {}))
    return metadata
