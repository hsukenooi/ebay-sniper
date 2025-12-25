#!/usr/bin/env python3
"""
Parser for bulk add input format.
Handles multiple input formats and deduplication.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import List, Tuple, Optional


def extract_listing_number(text: str) -> Optional[str]:
    """
    Extract listing number from text.
    Supports:
    - Plain listing number (digits, typically 10-12 digits)
    - eBay URL format (https://www.ebay.com/itm/123456789)
    
    Returns listing number as string, or None if not found.
    """
    # Try URL format first (most specific)
    url_pattern = r'itm/(\d{8,})'  # At least 8 digits for eBay listing numbers
    url_match = re.search(url_pattern, text)
    if url_match:
        return url_match.group(1)
    
    # Try to find sequence of digits (listing number, typically 10-12 digits)
    # Look for longer sequences first to avoid matching prices
    # eBay listing numbers are usually 10-12 digits, so prefer those
    long_digits_match = re.search(r'\d{10,}', text)
    if long_digits_match:
        return long_digits_match.group(0)
    
    # Fallback: any sequence of 8+ digits
    digits_match = re.search(r'\d{8,}', text)
    if digits_match:
        return digits_match.group(0)
    
    return None


def parse_bulk_input(lines: List[str]) -> List[Tuple[int, str, Decimal, str]]:
    """
    Parse bulk input lines.
    
    Args:
        lines: List of input lines (from stdin)
        
    Returns:
        List of tuples: (row_number, listing_number, max_bid, original_line)
        Row numbers are 1-indexed. Duplicates are filtered (keep first occurrence).
    
    Raises:
        ValueError: If a line cannot be parsed (but continues processing other lines)
    """
    results = []
    seen_listings = set()
    duplicates = set()
    
    for line_num, line in enumerate(lines, start=1):
        original_line = line
        
        # Strip whitespace
        line = line.strip()
        
        # Skip blank lines
        if not line:
            continue
        
        # Skip comment lines (starting with #)
        if line.startswith('#'):
            continue
        
        # Extract listing number
        listing_number = extract_listing_number(line)
        if not listing_number:
            # Line cannot be parsed - this is a parse error, but we'll include it in results
            # with a special marker
            results.append((line_num, None, None, original_line))
            continue
        
        # Check for duplicates (within the input)
        if listing_number in seen_listings:
            duplicates.add(line_num)
            results.append((line_num, listing_number, None, original_line))
            continue
        
        seen_listings.add(listing_number)
        
        # Extract max_bid - try multiple formats
        max_bid = None
        
        # Find the position of the listing number in the line
        listing_pos = line.find(listing_number)
        if listing_pos == -1:
            # Shouldn't happen, but handle it
            results.append((line_num, listing_number, None, original_line))
            continue
        
        # Get everything after the listing number
        after_listing = line[listing_pos + len(listing_number):].strip()
        
        # Try comma separator: listing,max_bid (comma immediately after listing number)
        if after_listing.startswith(','):
            bid_part = after_listing[1:].strip()  # Skip the comma
            try:
                max_bid = Decimal(bid_part.replace("$", "").replace(",", ""))
            except (InvalidOperation, ValueError):
                pass
        
        # Try tab separator
        if max_bid is None and '\t' in after_listing:
            parts = after_listing.split('\t', 1)
            bid_part = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            try:
                max_bid = Decimal(bid_part.replace("$", "").replace(",", ""))
            except (InvalidOperation, ValueError):
                pass
        
        # Try space separator (most common case - handles numbers with commas in them)
        if max_bid is None:
            # Try to find a number (potentially with decimal point and commas)
            # Match the longest number pattern possible (handles commas and decimals)
            # Pattern matches: digits, commas, optional decimal point and more digits
            bid_match = re.search(r'\$?\s*([\d,]+\.?\d*)', after_listing)
            if bid_match:
                try:
                    bid_str = bid_match.group(1).replace(",", "")
                    max_bid = Decimal(bid_str)
                except (InvalidOperation, ValueError):
                    pass
        
        # If still no max_bid found, this is a parse error
        if max_bid is None:
            results.append((line_num, listing_number, None, original_line))
            continue
        
        # Validate max_bid is positive
        if max_bid <= 0:
            results.append((line_num, listing_number, None, original_line))
            continue
        
        results.append((line_num, listing_number, max_bid, original_line))
    
    return results

