import sys
from dataclasses import dataclass

# import sqlparse - available if you need it!

database_file_path = sys.argv[1]
command = sys.argv[2]

if command == ".dbinfo":
    with open(database_file_path, "rb") as database_file:
        # Read the page size from the header
        database_file.seek(16)  # Skip the first 16 bytes of the header
        page_size = int.from_bytes(database_file.read(2), byteorder="big")
        print(f"database page size: {page_size}")

        # Read the number of tables from the header
        database_file.seek(103)
        cell_count = int.from_bytes(database_file.read(2), byteorder="big")
        print(f"number of tables: {cell_count}")
else:
    print(f"Invalid command: {command}")
