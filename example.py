import eeprom_93cx6

eeprom_93cx6.__DEBUG = False

# specify gpio pin of cs, sk, di, do
dev = eeprom_93cx6.Device(
    model=56,
    org=eeprom_93cx6.EEPROM_MODE_16BIT,
    cs=12,
    sk=13,
    di=14,
    do=15,
)


# dev.ew_enable()
#
# dev.write(0, 0x01)
# dev.write(1, 0x02)
# dev.write(2, 0x03)
#
# dev.ew_disable()

def dump_buffer(buf, start=0):
    num_lines = len(buf) // 8
    for nlines in range(num_lines):
        addr = (8 * nlines) + start
        print(f"0x{addr:02X} ", end="")
        for v in buf[nlines * 8 : 8 * (nlines + 1)]:
            print(f"{v:04X} ", end="")
        print()


buf = dev.read_sequential(0, 128)

dump_buffer(buf, start=0)

