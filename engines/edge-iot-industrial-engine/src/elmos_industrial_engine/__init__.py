"""ELMOS Industrial IoT & Edge Protocol Engine Package."""

from .protocol_mapper import (
    CanFrame,
    DbcSignal,
    Endianness,
    IndustrialMappingResult,
    IndustrialProtocolMapper,
    IndustrialSafetyGate,
    IndustrialSafetyValidationResult,
    IndustrialTag,
    SparkplugMetric,
    build_modbus_rtu_frame,
    compute_crc16_modbus,
    decode_can_dbc_signal,
    parse_modbus_rtu_frame,
    verify_crc16_modbus,
)

__all__ = [
    "CanFrame",
    "DbcSignal",
    "Endianness",
    "IndustrialMappingResult",
    "IndustrialProtocolMapper",
    "IndustrialSafetyGate",
    "IndustrialSafetyValidationResult",
    "IndustrialTag",
    "SparkplugMetric",
    "build_modbus_rtu_frame",
    "compute_crc16_modbus",
    "decode_can_dbc_signal",
    "parse_modbus_rtu_frame",
    "verify_crc16_modbus",
]

