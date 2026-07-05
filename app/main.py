import sys
from dataclasses import dataclass
from typing import List, Tuple

# import sqlparse - available if you need it!

database_file_path = sys.argv[1]
command = sys.argv[2]


def read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """Read a varint from the data at the given offset. Returns the offset after the varint."""
    # SQLite varints are big-endian, 7 usable bits per byte: the top bit of
    # each byte just says "there's another byte after this one", so each
    # new byte's low 7 bits get shifted further left and OR'd in.
    value = 0
    for i in range(9):
        byte = data[offset + i]
        value |= (byte & 0x7F) << (7 * i)
        if byte & 0x80 == 0:  # top bit clear -> this was the last byte
            break
    # `i` is the index of the last byte read, so i + 1 bytes were consumed.
    return value, offset + i + 1


def serial_type_size(serial_type: int) -> int:
    """Return how many bytes this serial type's value occupies in the record body."""
    # Codes 0-9 are fixed-size types (NULL, ints of various widths, float,
    # and the "value is baked into the code" cases 8/9). Everything from 12
    # up is variable-length BLOB (even) or TEXT (odd), and the actual byte
    # length is packed into the code itself per the file format spec.
    if serial_type <= 4:
        return serial_type
    if serial_type == 5:
        return 6
    if serial_type in (6, 7):
        return 8
    if serial_type in (8, 9):
        return 0
    if serial_type >= 12 and serial_type % 2 == 0:
        return (serial_type - 12) // 2
    if serial_type >= 13 and serial_type % 2 == 1:
        return (serial_type - 13) // 2
    return 0


def read_serial_types(
    data: bytes, offset: int, header_end: int
) -> Tuple[List[int], int]:
    """Read varints from offset until the header_end is reached. Returns a list of serial types and the new offset."""
    # The record header is just a run of varints (one serial type per column)
    # packed back-to-back; header_end tells us where to stop.
    serial_types = []
    while offset < header_end:
        serial_type, offset = read_varint(data, offset)
        serial_types.append(serial_type)
    return serial_types, offset


if command == ".dbinfo":
    with open(database_file_path, "rb") as database_file:
        # Read the page size from the header
        database_file.seek(16)  # Skip the first 16 bytes of the header
        page_size = int.from_bytes(database_file.read(2), byteorder="big")
        print(f"database page size: {page_size}")

        # Read the number of cells from the header
        database_file.seek(103)
        cell_count = int.from_bytes(database_file.read(2), byteorder="big")
        print(f"number of tables: {cell_count}")
elif command == ".tables":
    with open(database_file_path, "rb") as database_file:
        # Read the number of cells from the header
        database_file.seek(103)
        cell_count = int.from_bytes(database_file.read(2), byteorder="big")

        # The cell pointer array sits right after the page header. Page 1
        # is special: it has the 100-byte database header in front of the
        # normal 8-byte b-tree page header, so the array starts at 108
        # instead of the usual 8. Offsets in the array are 2-byte
        # big-endian values, relative to the start of the page.
        cell_offsets = []
        for i in range(cell_count):
            database_file.seek(108 + i * 2)
            cell_offset = int.from_bytes(database_file.read(2), byteorder="big")
            cell_offsets.append(cell_offset)

        # Read the whole file into memory once so every offset below
        # can be used as-is, without re-seeking the file handle for every field.
        database_file.seek(0)
        data = database_file.read()
        for cell_offset in cell_offsets:
            # Each cell is: record size (varint), rowid (varint), record.
            # We don't need the record size or rowid for .tables, just
            # where they end so we know where the record header starts.
            _record_size, offset = read_varint(data, cell_offset)
            _rowid_value, offset = read_varint(data, offset)
            header_start = offset

            header_size, offset = read_varint(data, header_start)
            header_end = header_start + header_size
            serial_types, offset = read_serial_types(data, offset, header_end)

            # Column values are packed back-to-back right after the header,
            # in the same order as the serial types. sqlite_schema's
            # columns are (type, name, tbl_name, rootpage, sql), so we walk
            # past type and name to reach tbl_name at index 2.
            value_offset = offset
            for i, serial_type in enumerate(serial_types):
                size = serial_type_size(serial_type)
                if i == 2:
                    table_name = data[value_offset : value_offset + size].decode()
                    print(table_name)
                    break
                value_offset += size
else:
    print(f"Invalid command: {command}")
