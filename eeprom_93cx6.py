"""eeprom_93cx6
A micropython library to interface with EEPROM 93cx6 series.
"""

from utime import sleep_us as usleep
from machine import Pin


__DEBUG = False


def debug(tag, content):
    if __DEBUG:
        print(f"{tag}: {content}")


DELAY_CS = 0
DELAY_READ = 1
DELAY_WRITE = 1
DELAY_WAIT = 1

EEPROM_MODE_8BIT = 1
EEPROM_MODE_16BIT = 2


class OP:
    CONTROL: int = 0x00
    WRITE: int = 0x01
    READ: int = 0x02
    ERASE: int = 0x03


class CC:
    EW_DISABLE: int = 0x00
    WRITE_ALL: int = 0x01
    ERASE_ALL: int = 0x02
    EW_ENABLE: int = 0x03


class Device:
    """A class represents 93cx6 chip.
     VCC
      | NC(Don't Care)
      |  | TEST(Don't Care)
      |  |  | GND
      |  |  |  |
    __|__|__|__|__
    | |  |  |  | |
    | 8  7  6  5 |
    |            |
    |.1  2  3  4 |
    |_|__|__|__|_|
      |  |  |  |
      |  |  |  DO(Data Out)
      |  |  DI(Data In)
      | SK(Serial clocK)
     CS(Chip Select)
    """

    def __init__(self, model, cs, sk, di, do, org=EEPROM_MODE_16BIT):
        self.model = model
        if model not in [46, 56, 66, 76, 86]:
            raise ValueError(
                f"Device.model mismatch({model}): supported model are 46, 56, 66, 76, 86."
            )
        self.org = org
        if org not in [EEPROM_MODE_8BIT, EEPROM_MODE_16BIT]:
            raise ValueError(
                f"Device.org must be `EEPROM_MODE_8BIT` or `EEPROM_MODE_16BIT`, given value: {org}"
            )
        self.cs = Pin(cs, Pin.OUT)
        self.sk = Pin(sk, Pin.OUT)
        self.di = Pin(di, Pin.OUT)
        self.do = Pin(do, Pin.IN)
        self.bytes = Device.get_bytes_by_model(org, model)
        self.addr = Device.get_addr_by_model(org, model)
        self.mask = Device.get_mask_by_model(org, model)
        self._ew = False

    @staticmethod
    def get_bytes_by_model(org: int, model: int) -> int:
        if org == EEPROM_MODE_8BIT:
            byte = 128
        elif org == EEPROM_MODE_16BIT:
            byte = 64

        if model == 56:  # 256/128
            byte *= 2
        elif model == 66:  # 512/256
            byte *= 4
        elif model == 76:  # 1024/512
            byte *= 8
        elif model == 86:  # 2048/1024
            byte *= 16
        return byte

    @staticmethod
    def get_addr_by_model(org: int, model: int) -> int:
        if org == EEPROM_MODE_8BIT:
            addr = 7
        elif org == EEPROM_MODE_16BIT:
            addr = 6

        if model == 56 or model == 66:  # 9/8
            addr += 2
        if model == 76 or model == 86:  # 11/10
            addr += 4
        return addr

    @staticmethod
    def get_mask_by_model(org: int, model: int) -> int:
        if org == EEPROM_MODE_8BIT:
            mask = 0x7F
        elif org == EEPROM_MODE_16BIT:
            mask = 0x3F
        if model == 56 or model == 66:  # 0x1ff/0xff
            mask = (mask << 2) + 0x03
        if model == 76 or model == 86:  # 0x7ff/0x3ff
            mask = (mask << 4) + 0x0F
        return mask

    def validate_addr(self, addr):
        """Validate if given address is in range of memory space"""
        if addr < 0 or addr > (self.bytes - 1):  # address is 0-origin
            raise ValueError(f"Address exceeds maximum address({self.addr:04x})")

    def send_bits(self, value: int, length: int):
        """Send value through a DI pin"""
        for i in range(length - 1, -1, -1):
            send_bit = value & 1 << i
            if send_bit:
                self.di.on()
            else:
                self.di.off()
            usleep(DELAY_WRITE)
            self.sk.on()
            usleep(DELAY_WRITE)
            self.sk.off()
            usleep(DELAY_WRITE)

    def wait_ready(self):
        """Wait for EEPROM to verify a written value"""
        debug("wait_ready", "setting cs to high")
        self.cs.on()
        debug("wait_ready", "set cs to high, waiting dev_do to low")
        while self.do.value() != 1:
            usleep(DELAY_WAIT)
        self.cs.off()

    def ew_enable(self):
        """Enable Erase/Write feature(EWEN)"""
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)
        self.send_bits(
            OP.CONTROL << self.addr | CC.EW_ENABLE << (self.addr - 2), self.addr + 2
        )
        self.cs.off()
        self._ew = True

    def ew_disable(self) -> None:
        """Disable Erase/Write feature(EWDS)"""
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bit
        self.send_bits(
            OP.CONTROL << self.addr | CC.EW_ENABLE << (self.addr - 2), self.addr + 2
        )
        self.cs.off()
        self._ew = False

    def ew_enabled(self) -> bool:
        """Return if Erase/Write is enabled"""
        return self._ew

    def erase_all(self) -> None:
        """Perform a ERASE ALL feature"""
        if not self.ew_enabled():
            return
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bit
        self.send_bits(
            OP.CONTROL << self.addr | CC.ERASE_ALL << (self.addr - 2), self.addr + 2
        )
        self.cs.off()
        self.wait_ready()

    def erase(self, addr: int) -> None:
        """Erase a value of given address"""
        if not self.ew_enabled():
            return
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bit
        self.send_bits(OP.ERASE << self.addr | (addr & self.mask), self.addr + 2)
        self.cs.off()
        self.wait_ready()

    def write_all(self, value):
        """Perform a WRITE ALL feature with given value"""
        if not self.ew_enabled():
            return
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bit
        self.send_bits(
            OP.CONTROL << self.addr | CC.WRITE_ALL << (self.addr - 2), self.addr + 2
        )
        if self.org == EEPROM_MODE_16BIT:
            self.send_bits(0xFFFF & value, 16)
        elif self.org == EEPROM_MODE_8BIT:
            self.send_bits(0xFF & value, 8)
        self.cs.off()
        self.wait_ready()

    def write(self, addr: int, value: int) -> None:
        """Write value to given address"""
        if not self.ew_enabled():
            return
        self.validate_addr(addr)

        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bits
        self.send_bits(OP.WRITE << self.addr | (addr & self.mask), self.addr + 2)
        if self.org == EEPROM_MODE_16BIT:
            self.send_bits(0xFFFF & value, 16)
        elif self.org == EEPROM_MODE_8BIT:
            self.send_bits(0xFFFF & value, 8)
        self.cs.off()
        self.wait_ready()

    def read(self, addr: int) -> int:
        """Read a value of given address from EEPROM"""
        self.validate_addr(addr)

        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bit

        self.send_bits(OP.READ << self.addr | (addr & self.mask), self.addr + 2)

        if self.org == EEPROM_MODE_16BIT:
            num_bits = 16
        elif self.org == EEPROM_MODE_8BIT:
            num_bits = 8

        read_value = 0
        for i in range(num_bits, 0, -1):
            self.sk.on()
            usleep(DELAY_READ)
            read_bit = self.do.value()
            self.sk.off()
            usleep(DELAY_READ)
            read_value = read_value | (read_bit << (i - 1))
        self.cs.off()
        return read_value

    def read_sequential(self, addr: int, length: int):
        """Perform a sequential read of given address and length.
        Returns a list of values.
        If address exceeds maximum memory adderss, this function will stop and
        return a list at that time."""
        self.validate_addr(addr)

        arr = []
        self.cs.on()
        usleep(DELAY_CS)
        self.send_bits(1, 1)  # start bits
        self.send_bits(OP.READ << self.addr | (addr & self.mask), self.addr + 2)
        if self.org == EEPROM_MODE_16BIT:
            num_bits = 16
        elif self.org == EEPROM_MODE_8BIT:
            num_bits = 8

        for count in range(length):
            read_value = 0
            if addr + count > self.bytes:
                break
            for i in range(num_bits, 0, -1):
                self.sk.on()
                usleep(DELAY_READ)
                read_bit = self.do.value()
                self.sk.off()
                usleep(DELAY_READ)
                read_value = read_value | (read_bit << (i - 1))
            arr.append(read_value)

        self.cs.off()
        return arr
