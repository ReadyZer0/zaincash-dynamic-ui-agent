"""Small QR Model 2 encoder for local, non-payable mock receive codes."""

from __future__ import annotations

SIZE = 25
DATA_CODEWORDS = 34
ECC_CODEWORDS = 10
MAX_PAYLOAD_BYTES = 32


def _multiply(left: int, right: int) -> int:
    """Multiply in GF(256) using the QR primitive polynomial 0x11D."""
    product = 0
    while right:
        if right & 1:
            product ^= left
        right >>= 1
        left <<= 1
        if left & 0x100:
            left ^= 0x11D
    return product


def _remainder(data: list[int]) -> list[int]:
    generator = [1]
    root = 1
    for _ in range(ECC_CODEWORDS):
        new = [0] * (len(generator) + 1)
        for index, coefficient in enumerate(generator):
            new[index] ^= coefficient
            new[index + 1] ^= _multiply(coefficient, root)
        generator = new
        root = _multiply(root, 2)
    result = [0] * ECC_CODEWORDS
    for value in data:
        factor = value ^ result[0]
        result = result[1:] + [0]
        for index, coefficient in enumerate(generator[1:]):
            result[index] ^= _multiply(coefficient, factor)
    return result


def encode(payload: str) -> list[list[int]]:
    """Encode 1..32 ASCII bytes as QR version 2, error level L, mask 0."""
    raw = payload.encode("ascii")
    if not raw or len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload must contain 1..{MAX_PAYLOAD_BYTES} ASCII bytes")
    bits: list[int] = []

    def append(value: int, count: int) -> None:
        bits.extend((value >> shift) & 1 for shift in range(count - 1, -1, -1))

    append(0b0100, 4)  # byte mode
    append(len(raw), 8)
    for byte in raw:
        append(byte, 8)
    capacity = DATA_CODEWORDS * 8
    bits.extend([0] * min(4, capacity - len(bits)))
    bits.extend([0] * (-len(bits) % 8))
    data = [
        sum(bit << (7 - i) for i, bit in enumerate(bits[start : start + 8]))
        for start in range(0, len(bits), 8)
    ]
    pads = (0xEC, 0x11)
    while len(data) < DATA_CODEWORDS:
        data.append(pads[(len(data) - len(bits) // 8) % 2])
    stream = data + _remainder(data)
    stream_bits = [(byte >> shift) & 1 for byte in stream for shift in range(7, -1, -1)]
    matrix: list[list[int | None]] = [[None] * SIZE for _ in range(SIZE)]

    def put(row: int, column: int, value: bool) -> None:
        matrix[row][column] = int(value)

    def finder(center_row: int, center_column: int) -> None:
        for delta_row in range(-4, 5):
            for delta_column in range(-4, 5):
                row = center_row + delta_row
                column = center_column + delta_column
                if 0 <= row < SIZE and 0 <= column < SIZE:
                    radius = max(abs(delta_row), abs(delta_column))
                    put(row, column, radius not in (2, 4))

    finder(3, 3)
    finder(3, SIZE - 4)
    finder(SIZE - 4, 3)
    for delta_row in range(-2, 3):
        for delta_column in range(-2, 3):
            radius = max(abs(delta_row), abs(delta_column))
            put(18 + delta_row, 18 + delta_column, radius != 1)
    for index in range(8, SIZE - 8):
        put(6, index, index % 2 == 0)
        put(index, 6, index % 2 == 0)

    # Format information: error-correction L and mask pattern 0.
    format_data = 0b01000
    remainder = format_data << 10
    for shift in range(14, 9, -1):
        if (remainder >> shift) & 1:
            remainder ^= 0x537 << (shift - 10)
    format_bits = ((format_data << 10) | remainder) ^ 0x5412

    def format_bit(index: int) -> bool:
        return ((format_bits >> index) & 1) != 0

    for index in range(6):
        put(index, 8, format_bit(index))
    put(7, 8, format_bit(6))
    put(8, 8, format_bit(7))
    put(8, 7, format_bit(8))
    for index in range(9, 15):
        put(8, 14 - index, format_bit(index))
    for index in range(8):
        put(8, SIZE - 1 - index, format_bit(index))
    for index in range(8, 15):
        put(SIZE - 15 + index, 8, format_bit(index))
    put(SIZE - 8, 8, True)  # fixed dark module

    bit_index = 0
    upward = True
    right = SIZE - 1
    while right >= 1:
        if right == 6:
            right -= 1
        for step in range(SIZE):
            row = SIZE - 1 - step if upward else step
            for offset in range(2):
                column = right - offset
                if matrix[row][column] is not None:
                    continue
                value = stream_bits[bit_index] if bit_index < len(stream_bits) else 0
                bit_index += 1
                if (row + column) % 2 == 0:
                    value ^= 1
                matrix[row][column] = value
        upward = not upward
        right -= 2
    return [[int(cell or 0) for cell in row] for row in matrix]
