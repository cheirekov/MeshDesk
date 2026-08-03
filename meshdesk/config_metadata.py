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
    ("position", "position_flags"): {
        "label": "Данни в position пакетите",
        "default": "0 · firmware избира основния position payload",
        "minimum": 0,
        "maximum": 1023,
        "value_format": "bitmask",
        "flags": [
            {"value": 1, "label": "Altitude"},
            {"value": 2, "label": "Altitude is MSL"},
            {"value": 4, "label": "Geoidal separation"},
            {"value": 8, "label": "DOP / PDOP"},
            {"value": 16, "label": "Separate HDOP + VDOP"},
            {"value": 32, "label": "Satellites in view"},
            {"value": 64, "label": "Sequence number"},
            {"value": 128, "label": "GPS timestamp"},
            {"value": 256, "label": "Heading"},
            {"value": 512, "label": "Speed"},
        ],
        "recommended": (
            "Включи само нужните полета; всяко допълнение увеличава position payload-а "
            "и LoRa airtime-а"
        ),
        "note": "Стойността е сбор (bitwise OR), а не избор на един режим.",
        "enforce_range": True,
    },
    ("power", "powermon_enables"): {
        "label": "Power-monitor debug източници",
        "default": "0 · изключени power-monitor logs",
        "value_format": "bitmask",
        "recommended": "0, освен при целенасочена hardware диагностика",
        "note": (
            "Това е firmware bitmask за debug log източници. Битовете са "
            "hardware/firmware-зависими и MeshDesk умишлено не им измисля универсални имена."
        ),
    },
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
    ("lora", "bandwidth"): {
        "default": "0 · определя се от Modem preset",
        "unit": "kHz",
        "recommended": "Остави 0, когато Use preset е включено",
        "note": "Използва се само при custom modem configuration.",
    },
    ("lora", "spread_factor"): {
        "default": "0 · определя се от Modem preset",
        "minimum": 0,
        "maximum": 12,
        "choices": [
            {"value": 0, "label": "0 · от Modem preset"},
            *[
                {"value": value, "label": f"SF{value} · custom modem"}
                for value in range(5, 13)
            ],
        ],
        "recommended": "Остави 0, когато Use preset е включено; custom стойностите са RF advanced",
        "note": "SF5–SF6 изискват по-нов LoRa chip; SX127x/RF95 обикновено поддържа SF7–SF12.",
        "enforce_range": True,
        "enforce_choices": True,
    },
    ("lora", "coding_rate"): {
        "default": "0 · определя се от Modem preset",
        "minimum": 0,
        "maximum": 8,
        "choices": [
            {"value": 0, "label": "0 · от Modem preset"},
            *[
                {"value": value, "label": f"4/{value} · custom modem"}
                for value in range(5, 9)
            ],
        ],
        "recommended": "Остави 0, когато Use preset е включено",
        "note": "Използва се само при custom modem configuration.",
        "enforce_range": True,
        "enforce_choices": True,
    },
    ("lora", "channel_num"): {
        "default": "0 · automatic channel slot от channel name и region",
        "recommended": "0 за автоматичен избор; ръчна стойност само при координиран frequency plan",
        "note": "Допустимият брой slots зависи от избрания region.",
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
    ("position", "gps_attempt_time"): {
        "default": "deprecated",
        "unit": "s",
        "recommended": "Не променяй; firmware използва smart/regular broadcast intervals",
        "note": "Полето е deprecated в protobuf спецификацията.",
    },
    ("display", "screen_on_secs"): {
        "default": "600 s за обикновен node; 1 s за ROUTER/ROUTER_LATE",
        "unit": "s",
        "recommended": "30–600 s според захранването и нуждата от локален дисплей",
    },
    ("display", "auto_screen_carousel_secs"): {
        "default": "0 · carousel изключен",
        "minimum": 0,
        "unit": "s",
        "value_format": "duration",
        "recommended": "0 за ръчно превключване или удобен интервал според броя screen pages",
    },
    ("power", "on_battery_shutdown_after_secs"): {
        "default": "0 · не изключвай автоматично",
        "minimum": 0,
        "unit": "s",
        "value_format": "duration_zero_disabled",
        "recommended": "0, освен ако умишлено искаш shutdown след отпадане на външното захранване",
    },
    ("bluetooth", "fixed_pin"): {
        "label": "Fixed Bluetooth PIN",
        "minimum": 100000,
        "maximum": 999999,
        "recommended": "Случаен 6-цифрен PIN; не използвай лесни последователности",
        "note": "Използва се само при pairing mode FIXED_PIN.",
        "enforce_range": True,
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
    ("paxcounter", "paxcounter_update_interval"): {
        "unit": "s",
        "value_format": "duration",
        "recommended": "По-дълъг интервал намалява airtime; избери според реалната нужда от броене",
    },
    ("external_notification", "output_ms"): {
        "default": "1000 ms · 1 секунда",
        "unit": "ms",
        "recommended": "1000 ms като начална стойност",
    },
    ("external_notification", "nag_timeout"): {
        "default": "0 · без повторение",
        "unit": "s",
        "value_format": "duration_zero_disabled",
        "recommended": "0, освен ако повторното известяване е необходимо",
    },
    ("range_test", "sender"): {
        "default": "0 · не изпраща range-test пакети",
        "unit": "s",
        "value_format": "duration_zero_disabled",
        "recommended": "0 извън контролиран range test; тестовият traffic използва airtime",
    },
    ("detection_sensor", "minimum_broadcast_secs"): {
        "unit": "s",
        "value_format": "duration",
        "recommended": "Достатъчно дълъг интервал, за да не flood-ва mesh-а при чест trigger",
    },
    ("detection_sensor", "state_broadcast_secs"): {
        "unit": "s",
        "value_format": "duration",
        "recommended": "Съобрази с нужната свежест и LoRa airtime budget-а",
    },
    ("ambient_lighting", "red"): {
        "minimum": 0,
        "maximum": 255,
        "unit": "RGB",
        "enforce_range": True,
        "recommended": "0–255 според желания цвят и наличния LED хардуер",
    },
    ("ambient_lighting", "green"): {
        "minimum": 0,
        "maximum": 255,
        "unit": "RGB",
        "enforce_range": True,
        "recommended": "0–255 според желания цвят и наличния LED хардуер",
    },
    ("ambient_lighting", "blue"): {
        "minimum": 0,
        "maximum": 255,
        "unit": "RGB",
        "enforce_range": True,
        "recommended": "0–255 според желания цвят и наличния LED хардуер",
    },
    ("traffic_management", "position_precision_bits"): {
        "label": "Position precision ceiling",
        "minimum": 0,
        "maximum": 32,
        "value_format": "position_precision",
        "recommended": "Предпочитай channel Position precision; това поле е version-dependent",
        "note": "В по-новите protobuf версии precision се извежда от настройката на канала.",
        "enforce_range": True,
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
    if field.endswith("_secs") or field.endswith("_interval"):
        metadata.setdefault("unit", "s")
        metadata.setdefault("value_format", "duration")
    elif field.endswith("_ms"):
        metadata.setdefault("unit", "ms")
    if (
        field.endswith("_gpio")
        or field.endswith("_pin")
        or field in {"rxd", "txd", "inputbroker_pin_a", "inputbroker_pin_b"}
    ):
        metadata["domain"] = "GPIO номер според pinout-а на конкретната платка"
        metadata["recommended"] = (
            "Запази board default, освен ако си проверил схемата на точния hardware variant."
        )
    return metadata
