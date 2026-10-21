"""Focused tests for the local mock receive-QR encoder."""

from __future__ import annotations

import unittest

from qr_code import ECC_CODEWORDS, _remainder, encode


def _read_data_modules(matrix: list[list[int]]) -> list[int]:
    size = len(matrix)
    reserved = [[False] * size for _ in range(size)]

    def reserve(row: int, column: int) -> None:
        if 0 <= row < size and 0 <= column < size:
            reserved[row][column] = True

    def reserve_finder(center_row: int, center_column: int) -> None:
        for delta_row in range(-4, 5):
            for delta_column in range(-4, 5):
                reserve(center_row + delta_row, center_column + delta_column)

    reserve_finder(3, 3)
    reserve_finder(3, size - 4)
    reserve_finder(size - 4, 3)
    for row in range(16, 21):
        for column in range(16, 21):
            reserve(row, column)
    for index in range(8, size - 8):
        reserve(6, index)
        reserve(index, 6)
    for index in range(6):
        reserve(index, 8)
    for row, column in (
        (7, 8),
        (8, 8),
        (8, 7),
        *((8, 14 - index) for index in range(9, 15)),
        *((8, size - 1 - index) for index in range(8)),
        *((size - 15 + index, 8) for index in range(8, 15)),
        (size - 8, 8),
    ):
        reserve(row, column)

    bits: list[int] = []
    upward = True
    right = size - 1
    while right >= 1:
        if right == 6:
            right -= 1
        for step in range(size):
            row = size - 1 - step if upward else step
            for offset in range(2):
                column = right - offset
                if reserved[row][column]:
                    continue
                bit = matrix[row][column]
                if (row + column) % 2 == 0:
                    bit ^= 1
                bits.append(bit)
        upward = not upward
        right -= 2
    return bits


class QrCodeTests(unittest.TestCase):
    def test_mock_payload_produces_deterministic_binary_v2_matrix(self) -> None:
        payload = "MOCK-RECEIVE|AMINA|NOT-PAYABLE"
        matrix = encode(payload)

        self.assertEqual(matrix, encode(payload))
        self.assertEqual(len(matrix), 25)
        self.assertTrue(all(len(row) == 25 for row in matrix))
        self.assertTrue(all(cell in (0, 1) for row in matrix for cell in row))
        self.assertEqual(
            [row[:7] for row in matrix[:7]],
            [
                [1, 1, 1, 1, 1, 1, 1],
                [1, 0, 0, 0, 0, 0, 1],
                [1, 0, 1, 1, 1, 0, 1],
                [1, 0, 1, 1, 1, 0, 1],
                [1, 0, 1, 1, 1, 0, 1],
                [1, 0, 0, 0, 0, 0, 1],
                [1, 1, 1, 1, 1, 1, 1],
            ],
        )
        first_format = [matrix[index][8] for index in range(6)]
        first_format.extend((matrix[7][8], matrix[8][8], matrix[8][7]))
        first_format.extend(matrix[8][14 - index] for index in range(9, 15))
        self.assertEqual(
            sum(bit << index for index, bit in enumerate(first_format)), 0x77C4
        )

        stream_bits = _read_data_modules(matrix)
        codewords = [
            sum(
                bit << (7 - offset)
                for offset, bit in enumerate(stream_bits[start : start + 8])
            )
            for start in range(0, 44 * 8, 8)
        ]
        data = codewords[:-ECC_CODEWORDS]
        self.assertEqual(codewords[-ECC_CODEWORDS:], _remainder(data))
        self.assertEqual(stream_bits[:4], [0, 1, 0, 0])
        length = sum(
            bit << (7 - offset) for offset, bit in enumerate(stream_bits[4:12])
        )
        self.assertEqual(length, len(payload))
        decoded = bytes(
            sum(
                bit << (7 - offset)
                for offset, bit in enumerate(stream_bits[start : start + 8])
            )
            for start in range(12, 12 + length * 8, 8)
        ).decode("ascii")
        self.assertEqual(decoded, payload)

    def test_rejects_payload_outside_version_two_ascii_capacity(self) -> None:
        with self.assertRaises(ValueError):
            encode("")
        with self.assertRaises(ValueError):
            encode("X" * 33)
        with self.assertRaises(UnicodeEncodeError):
            encode("رمز")
