"""Протокол управления кондиционерами Haier."""
import struct
from enum import IntEnum
from typing import Optional
import logging

_LOGGER = logging.getLogger(__name__)


# ---------- Перечисления (как в оригинале) ----------
class Mode(IntEnum):
    AUTO = 0
    COOL = 1
    DRY = 2
    HEAT = 3
    FAN = 4


class FanSpeed(IntEnum):
    AUTO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Limits(IntEnum):
    NONE = 0
    # другие значения, если есть


# ---------- Класс состояния ----------
class State:
    """Состояние кондиционера."""
    def __init__(
        self,
        mode: int = Mode.AUTO,
        fan_speed: int = FanSpeed.AUTO,
        limits: int = Limits.NONE,
        health: bool = False,
        target_temperature: int = 24,
    ):
        self.mode = mode
        self.fan_speed = fan_speed
        self.limits = limits
        self.health = health
        self.target_temperature = target_temperature

    def __repr__(self):
        return (
            f"State(mode={self.mode}, fan_speed={self.fan_speed}, "
            f"limits={self.limits}, health={self.health}, "
            f"target_temperature={self.target_temperature})"
        )


# ---------- Основной класс протокола ----------
class HaierProtocol:
    """Реализация протокола Haier (совместима с оригинальной TS-библиотекой)."""

    def __init__(self, mac: str, device_type: int = 0x22):
        """
        :param mac: MAC-адрес устройства (например, "AA:BB:CC:DD:EE:FF")
        :param device_type: тип устройства (по умолчанию 0x22)
        """
        self._mac = mac.replace(":", "").lower()
        self._device_type = device_type
        self._seq = 0

    def _mac_address_bytes(self) -> bytes:
        """MAC-адрес в байтах с обратным порядком (как требует протокол)."""
        mac_clean = self._mac.replace(":", "")
        return bytes.fromhex(mac_clean)[::-1]

    def _next_seq(self) -> int:
        """Следующий порядковый номер пакета (0..255)."""
        self._seq = (self._seq + 1) % 256
        return self._seq

    def _build_packet(self, command: bytes, seq: int) -> bytes:
        """Упаковывает команду в полный пакет с заголовками и MAC-адресом."""
        header = bytes.fromhex("00 00 27 14 00 00 00 00")
        zeros1 = bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = struct.pack(">I", seq)          # 4 байта, big-endian
        cmd_len_bytes = struct.pack(">I", len(command))
        return header + zeros1 + mac_bytes + zeros2 + seq_bytes + cmd_len_bytes + command

    # ---------- Запрос состояния ----------
    def create_get_state_packet(self) -> bytes:
        """Создаёт пакет запроса текущего состояния."""
        seq = self._next_seq()
        # Фиксированный шаблон для запроса
        hex_str = (
            "ff ff 22 00 00 00 00 00 00 01 4d 5f "
            "00 00 00 00 00 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00"
        )
        # Контрольная сумма (как в оригинале)
        hex_clean = hex_str.replace(" ", "")
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        checksum = (total - 2 * 255) % 256
        hex_str += f" {checksum:02x}"
        command = bytes.fromhex(hex_str.replace(" ", ""))
        return self._build_packet(command, seq)

    # ---------- Установка состояния (ИСПРАВЛЕННАЯ ВЕРСИЯ) ----------
    def create_set_state_packet(self, state: State) -> bytes:
        """
        Создаёт пакет для установки состояния.
        Исправлено: правильная упаковка power+health (битовая маска) и устранён лишний байт health,
        благодаря чему температура попадает в нужное место.
        """
        seq = self._next_seq()

        # Базовый шаблон (22 байта)
        hex_str = "ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00"

        # word11 (grp6) – режим
        hex_str += f" 00 {state.mode:02x}"
        # word12 (grp7) – скорость вентилятора
        hex_str += f" 00 {state.fan_speed:02x}"
        # word13 (grp8) – лимиты
        hex_str += f" 00 {state.limits:02x}"

        # word14 (grp9) – power (бит 0 всегда 1) + health (бит 3)
        power_health = 0x01 | (0x08 if state.health else 0x00)
        hex_str += f" 00 {power_health:02x}"

        # word15 (grp10) – всегда 0
        hex_str += " 00 00"

        # word16 + word17 (grp11 + grp12) – температура (смещение -16)
        temp_offset = state.target_temperature - 16
        hex_str += f" 00 00 00 {temp_offset:02x}"

        # Контрольная сумма
        hex_clean = hex_str.replace(" ", "")
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        checksum = (total - 2 * 255) % 256
        hex_str += f" {checksum:02x}"

        command = bytes.fromhex(hex_str.replace(" ", ""))
        return self._build_packet(command, seq)

    # ---------- Разбор ответа ----------
    def parse_response(self, data: bytes) -> Optional[State]:
        """
        Разбирает ответ от кондиционера и возвращает объект State.
        Возвращает None, если пакет некорректен.
        """
        if len(data) < 44:
            _LOGGER.warning("Слишком короткий пакет ответа")
            return None

        # Проверяем заголовок
        if data[0:4] != b'\x00\x00\x27\x14':
            _LOGGER.warning("Неверный заголовок ответа")
            return None

        # Смещение до команды: 8 (header) + 16 (нули) + 6 (MAC) + 16 (нули) + 4 (seq) + 4 (длина) = 54
        offset = 8 + 16 + 6 + 16 + 4 + 4
        if len(data) < offset:
            _LOGGER.warning("Недостаточно данных для извлечения команды")
            return None

        cmd = data[offset:]
        if len(cmd) < 42:
            _LOGGER.warning("Команда ответа слишком короткая")
            return None

        # Сигнатура команды
        if cmd[0:3] != b'\xff\xff\x22':
            _LOGGER.warning("Неверная сигнатура команды ответа")
            return None

        # Извлекаем значения (индексы байтов внутри команды)
        mode = cmd[24] if len(cmd) > 24 else 0
        fan_speed = cmd[26] if len(cmd) > 26 else 0
        # limits – cmd[28] (word13), но обычно не используется
        power_health = cmd[30] if len(cmd) > 30 else 0
        health = bool(power_health & 0x08)
        temp_raw = cmd[36] if len(cmd) > 36 else 0
        target_temperature = temp_raw + 16

        state = State(
            mode=mode,
            fan_speed=fan_speed,
            limits=Limits.NONE,   # можно заменить на cmd[28] при необходимости
            health=health,
            target_temperature=target_temperature,
        )
        return state
