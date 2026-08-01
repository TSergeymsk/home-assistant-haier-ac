"""
Протокол управления кондиционерами Haier (совместим с оригинальной TS-библиотекой)
"""
import struct
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class State:
    """Класс состояния кондиционера (должен совпадать с вашим определением)"""
    def __init__(self, mode=0, fan_speed=0, limits=0, health=False, target_temperature=24):
        self.mode = mode
        self.fan_speed = fan_speed
        self.limits = limits
        self.health = health
        self.target_temperature = target_temperature


class HaierProtocol:
    """Реализация протокола управления кондиционерами Haier"""
    
    def __init__(self, mac: str, device_type: int = 0x22):
        """
        :param mac: MAC-адрес устройства в виде строки (например, "AA:BB:CC:DD:EE:FF")
        :param device_type: тип устройства (по умолчанию 0x22)
        """
        self._mac = mac.replace(":", "").lower()
        self._device_type = device_type
        self._seq = 0  # счётчик для команд

    def _mac_address_bytes(self) -> bytes:
        """Преобразует MAC-адрес в байты (в обратном порядке, как требует протокол)"""
        mac_clean = self._mac.replace(":", "")
        # разбиваем по 2 символа и переворачиваем
        mac_bytes = bytes.fromhex(mac_clean)[::-1]
        return mac_bytes

    def _next_seq(self) -> int:
        """Возвращает следующий порядковый номер пакета"""
        self._seq = (self._seq + 1) % 256
        return self._seq

    def create_get_state_packet(self) -> bytes:
        """Создаёт пакет запроса текущего состояния"""
        seq = self._next_seq()
        # Запрос состояния — фиксированный шаблон
        hex_str = "ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00"
        hex_str += " 00 00 00 00 00 00 00 00 00 00 00 00"  # 12 нулевых байт
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
        # Упаковка в полный пакет
        return self._build_packet(command, seq)

    def create_set_state_packet(self, state: State) -> bytes:
        """
        Создаёт пакет для установки состояния.
        Исправленная версия – соответствует оригинальной TS-библиотеке.
        """
        seq = self._next_seq()
        # Базовый шаблон (22 байта команды)
        hex_str = "ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00"
        
        # word11 (grp6) – режим
        hex_str += f" 00 {state.mode:02x}"
        # word12 (grp7) – скорость вентилятора
        hex_str += f" 00 {state.fan_speed:02x}"
        # word13 (grp8) – лимиты (обычно 0)
        hex_str += f" 00 {state.limits:02x}"
        
        # word14 (grp9) – power (бит0) + health (бит3)
        power_health = 0x01 | (0x08 if state.health else 0x00)
        hex_str += f" 00 {power_health:02x}"
        
        # word15 (grp10) – всегда 0
        hex_str += " 00 00"
        
        # word16 + word17 (grp11 + grp12) – температура (смещение -16)
        temp_offset = state.target_temperature - 16
        hex_str += f" 00 00 00 {temp_offset:02x}"
        
        # Расчёт контрольной суммы (как в оригинале)
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

    def _build_packet(self, command: bytes, seq: int) -> bytes:
        """Упаковывает команду в полный пакет с заголовками и MAC-адресом"""
        header = bytes.fromhex("00 00 27 14 00 00 00 00")
        zeros1 = bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = struct.pack(">I", seq)  # 4 байта, big-endian
        cmd_len = len(command)
        cmd_len_bytes = struct.pack(">I", cmd_len)
        return header + zeros1 + mac_bytes + zeros2 + seq_bytes + cmd_len_bytes + command

    def parse_response(self, data: bytes) -> Optional[State]:
        """
        Разбирает ответ от кондиционера и возвращает объект State.
        Возвращает None, если пакет некорректен.
        """
        if len(data) < 44:
            _LOGGER.warning("Слишком короткий пакет ответа")
            return None
        # Проверяем сигнатуру
        if data[0:4] != b'\x00\x00\x27\x14':
            _LOGGER.warning("Неверный заголовок ответа")
            return None
        # Извлекаем полезную нагрузку (команду) – смещение зависит от структуры
        # В оригинальной библиотеке: заголовок 8 байт, потом 16 нулей, MAC (6), 16 нулей,
        # seq (4), длина (4), затем команда.
        # Ищем начало команды: после всех заголовков
        # Проще: пропускаем 8 + 16 + 6 + 16 + 4 + 4 = 54 байта
        offset = 8 + 16 + 6 + 16 + 4 + 4
        if len(data) < offset:
            _LOGGER.warning("Недостаточно данных для извлечения команды")
            return None
        cmd = data[offset:]
        # Минимальная длина команды для состояния
        if len(cmd) < 42:
            _LOGGER.warning("Команда ответа слишком короткая")
            return None
        # Проверяем начало команды (должно быть ff ff 22 ...)
        if cmd[0:3] != b'\xff\xff\x22':
            _LOGGER.warning("Неверная сигнатура команды ответа")
            return None
        # Извлекаем байты состояния (по смещениям из оригинальной библиотеки)
        # word11 (индекс 24 в команде) - режим
        # word12 (26) - скорость вентилятора
        # word14 (30) - power + health
        # word17 (36) - температура (смещение -16)
        # Индексы в байтах (каждый word – 2 байта, но значения только в младшем байте)
        mode = cmd[24] if len(cmd) > 24 else 0
        fan_speed = cmd[26] if len(cmd) > 26 else 0
        # limits (word13) – не используется, обычно 0
        # power_health = cmd[30]
        power_health = cmd[30] if len(cmd) > 30 else 0
        health = bool(power_health & 0x08)
        temp_raw = cmd[36] if len(cmd) > 36 else 0
        target_temperature = temp_raw + 16
        # Создаём объект состояния
        state = State(
            mode=mode,
            fan_speed=fan_speed,
            limits=0,
            health=health,
            target_temperature=target_temperature
        )
        return state
