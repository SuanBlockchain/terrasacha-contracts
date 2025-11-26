"""
Transaction Metadata Utilities

This module provides utilities for preparing transaction metadata in various formats:
- CIP-20: Standard message metadata format (label 674)
- Custom: Flexible metadata with custom labels

Reference:
- CIP-20: https://cips.cardano.org/cips/cip20/
- Cardano Metadata: https://developers.cardano.org/docs/transaction-metadata/
"""

import pycardano as pc
from typing import Any


def convert_metadata_keys(metadata: dict) -> dict:
    """
    Convert string keys to integers for PyCardano metadata.

    PyCardano requires all metadata keys to be integers. This function
    recursively converts string representations of integers to actual integers.

    Args:
        metadata: Dictionary with potentially string keys

    Returns:
        Dictionary with integer keys where applicable

    Example:
        >>> convert_metadata_keys({"674": {"msg": ["Hello"]}})
        {674: {"msg": ["Hello"]}}
    """
    def convert_dict(d: Any) -> Any:
        if isinstance(d, dict):
            return {
                (int(k) if isinstance(k, str) and k.isdigit() else k): convert_dict(v)
                for k, v in d.items()
            }
        elif isinstance(d, list):
            return [convert_dict(item) for item in d]
        return d

    return convert_dict(metadata)


def prepare_cip20_metadata(message: str | list[str], additional_fields: dict | None = None) -> pc.AuxiliaryData:
    """
    Prepare CIP-20 standard message metadata.

    CIP-20 defines a standard format for general transaction metadata using label 674.
    Messages should be broken into chunks of max 64 characters.

    Args:
        message: Single message string or list of message chunks
        additional_fields: Optional additional fields to include in metadata

    Returns:
        AuxiliaryData ready to attach to transaction

    Example:
        >>> metadata = prepare_cip20_metadata("Hello from Terrasacha!")
        >>> builder.auxiliary_data = metadata

    CIP-20 Format:
        {
            "674": {
                "msg": ["Message", "chunks", "here"],
                // optional additional fields
            }
        }
    """
    # Convert message to list of chunks if it's a string
    if isinstance(message, str):
        # Break into chunks of 64 characters (CIP-20 recommendation)
        message_chunks = [message[i:i+64] for i in range(0, len(message), 64)]
    else:
        message_chunks = message

    # Build CIP-20 metadata structure
    cip20_metadata = {
        "674": {
            "msg": message_chunks
        }
    }

    # Add any additional fields
    if additional_fields:
        cip20_metadata["674"].update(additional_fields)

    # Convert to PyCardano format
    converted_metadata = convert_metadata_keys(cip20_metadata)
    metadata_obj = pc.Metadata(converted_metadata)
    alonzo_metadata = pc.AlonzoMetadata(metadata=metadata_obj)

    return pc.AuxiliaryData(alonzo_metadata)


def prepare_custom_metadata(metadata_dict: dict) -> pc.AuxiliaryData:
    """
    Prepare custom transaction metadata with flexible structure.

    Allows using any metadata label (0-8191 available for general use).
    Common labels:
    - 0-8191: Available for general use
    - 674: CIP-20 message metadata
    - 721: CIP-25 NFT metadata

    Args:
        metadata_dict: Dictionary with metadata structure
                      Keys can be string numbers (will be converted to int)

    Returns:
        AuxiliaryData ready to attach to transaction

    Example:
        >>> metadata = prepare_custom_metadata({
        ...     "1337": {
        ...         "app": "Terrasacha",
        ...         "version": "1.0",
        ...         "data": {"project_id": "PRJ-001"}
        ...     }
        ... })
        >>> builder.auxiliary_data = metadata
    """
    # Convert string keys to integers
    converted_metadata = convert_metadata_keys(metadata_dict)

    # Create PyCardano metadata objects
    metadata_obj = pc.Metadata(converted_metadata)
    alonzo_metadata = pc.AlonzoMetadata(metadata=metadata_obj)

    return pc.AuxiliaryData(alonzo_metadata)


def prepare_metadata(metadata_input: dict) -> pc.AuxiliaryData | None:
    """
    Smart metadata preparation that auto-detects CIP-20 or custom format.

    This function examines the input and determines the best way to prepare
    the metadata:
    - If "msg" field is present at root level → CIP-20 format
    - If numeric labels are present → Custom format
    - Otherwise → Wrap in custom metadata with default label

    Args:
        metadata_input: Dictionary with metadata content

    Returns:
        AuxiliaryData or None if metadata is empty

    Example CIP-20:
        >>> prepare_metadata({"msg": "Hello world"})

    Example Custom:
        >>> prepare_metadata({"1337": {"data": "value"}})
    """
    if not metadata_input:
        return None

    # Check if this looks like CIP-20 format (has "msg" field)
    if "msg" in metadata_input:
        message = metadata_input["msg"]
        additional_fields = {k: v for k, v in metadata_input.items() if k != "msg"}
        return prepare_cip20_metadata(message, additional_fields if additional_fields else None)

    # Otherwise treat as custom metadata
    return prepare_custom_metadata(metadata_input)


def extract_metadata_from_transaction(tx: pc.Transaction) -> dict | None:
    """
    Extract metadata from a Cardano transaction.

    Args:
        tx: PyCardano Transaction object

    Returns:
        Dictionary with metadata or None if no metadata present
    """
    if not tx.auxiliary_data or not tx.auxiliary_data.data:
        return None

    if not tx.auxiliary_data.data.metadata:
        return None

    # Extract metadata from transaction
    return dict(tx.auxiliary_data.data.metadata)


# Metadata validation constants
MAX_METADATA_SIZE = 16_384  # 16KB max per transaction
MAX_STRING_LENGTH = 64  # Recommended max string length per CIP-20


def validate_metadata_size(metadata: dict) -> tuple[bool, str]:
    """
    Validate that metadata doesn't exceed Cardano limits.

    Args:
        metadata: Metadata dictionary to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Convert to CBOR to check actual size
        aux_data = prepare_metadata(metadata)
        if not aux_data:
            return True, ""

        cbor_size = len(aux_data.to_cbor())

        if cbor_size > MAX_METADATA_SIZE:
            return False, f"Metadata size ({cbor_size} bytes) exceeds maximum ({MAX_METADATA_SIZE} bytes)"

        return True, ""
    except Exception as e:
        return False, f"Metadata validation error: {str(e)}"
