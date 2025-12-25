#!/usr/bin/env python3
import click
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from .client import SniperClient
from .config import save_token, get_timezone
from .bulk_parser import parse_bulk_input
import sys


@click.group()
def cli():
    """eBay Bid Sniping System CLI"""
    pass


@cli.command()
@click.option("--username", prompt="Username")
@click.option("--password", prompt="Password", hide_input=True)
def auth(username, password):
    """Authenticate with the server."""
    try:
        client = SniperClient()
        token = client.authenticate(username, password)
        save_token(token)
        click.echo("Authentication successful!")
    except Exception as e:
        click.echo(f"Authentication failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("listing_number")
@click.argument("max_bid", type=str)
def add(listing_number, max_bid):
    """Add a new listing for an auction."""
    try:
        max_bid_decimal = Decimal(max_bid.replace("$", "").replace(",", ""))
        client = SniperClient()
        result = client.add_sniper(listing_number, max_bid_decimal)
        click.echo(f"Listing added for auction {result['id']}")
        click.echo(f"Item: {result['item_title']}")
        current_price = float(result['current_price']) if isinstance(result['current_price'], str) else result['current_price']
        click.echo(f"Current Bid: ${current_price:.2f}")
        click.echo(f"Max bid: ${result['max_bid']}")
        click.echo(f"Ends at: {client.to_local_time(result['auction_end_time_utc'])}")
        click.echo(f"URL: {result['listing_url']}")
    except InvalidOperation:
        click.echo(f"Invalid max_bid format: {max_bid}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Failed to add listing: {e}", err=True)
        sys.exit(1)


@cli.command("add-bulk")
def add_bulk():
    """Bulk add listings from stdin.
    
    Reads input from stdin until EOF. Supports multiple formats:
    - listing_number max_bid
    - listing_number,max_bid
    - listing_number<TAB>max_bid
    - https://www.ebay.com/itm/listing_number max_bid
    
    Ignores blank lines and lines starting with #.
    """
    try:
        # Read all input from stdin
        lines = sys.stdin.readlines()
        
        # Parse input
        parsed_items = parse_bulk_input(lines)
        
        # Separate valid items from duplicates/invalid
        valid_items = []
        row_mapping = {}  # Map row number to index in parsed_items for output
        
        seen_listings = set()
        for row_num, listing_number, max_bid, original_line in parsed_items:
            # Check if this is a duplicate from the parser (max_bid is None but listing_number is set)
            is_duplicate_from_parser = (listing_number is not None and max_bid is None and listing_number in seen_listings)
            
            if listing_number is None:
                # Invalid line - no listing number
                valid_items.append({
                    'row_num': row_num,
                    'listing_number': None,
                    'max_bid': None,
                    'original_line': original_line,
                    'is_duplicate': False
                })
                continue
            
            # Check for duplicates within input
            if listing_number in seen_listings or is_duplicate_from_parser:
                valid_items.append({
                    'row_num': row_num,
                    'listing_number': listing_number,
                    'max_bid': max_bid,  # May be None if duplicate from parser
                    'original_line': original_line,
                    'is_duplicate': True
                })
                continue
            
            # Check if max_bid is missing (parse error, not duplicate)
            if max_bid is None:
                valid_items.append({
                    'row_num': row_num,
                    'listing_number': listing_number,
                    'max_bid': None,
                    'original_line': original_line,
                    'is_duplicate': False
                })
                continue
            
            # Valid item
            seen_listings.add(listing_number)
            valid_items.append({
                'row_num': row_num,
                'listing_number': listing_number,
                'max_bid': max_bid,
                'original_line': original_line,
                'is_duplicate': False
            })
        
        # Prepare request payload (only valid, non-duplicate items)
        request_items = [
            {'listing_number': item['listing_number'], 'max_bid': float(item['max_bid'])}
            for item in valid_items
            if item['listing_number'] is not None and item['max_bid'] is not None and not item['is_duplicate']
        ]
        
        # Call server
        client = SniperClient()
        response = client.bulk_add_snipers(request_items)
        
        # Build results mapping by listing_number
        server_results = {r['listing_number']: r for r in response['results']}
        
        # Build output results
        output_results = []
        for item in valid_items:
            row_num = item['row_num']
            
            if item['is_duplicate']:
                output_results.append({
                    'row': row_num,
                    'listing': item['listing_number'],
                    'max_bid': f"{item['max_bid']:.2f}" if item['max_bid'] else '-',
                    'result': 'Duplicate',
                    'auction_id': '-',
                    'ends_at': '-',
                    'url': '-',
                    'reason': 'Duplicate listing in input'
                })
            elif item['listing_number'] is None or item['max_bid'] is None:
                output_results.append({
                    'row': row_num,
                    'listing': item.get('listing_number', 'Invalid') if item.get('listing_number') else 'Invalid',
                    'max_bid': '-',
                    'result': 'Error',
                    'auction_id': '-',
                    'ends_at': '-',
                    'url': '-',
                    'reason': 'Invalid format - could not parse listing number or max bid'
                })
            else:
                server_result = server_results.get(item['listing_number'])
                if server_result and server_result.get('success'):
                    # Success - handle datetime serialization
                    ends_at_str = '-'
                    if server_result.get('auction_end_time_utc'):
                        # Handle both string and datetime objects
                        ends_at = server_result['auction_end_time_utc']
                        if isinstance(ends_at, str):
                            ends_at_str = client.to_local_time(ends_at)
                        elif hasattr(ends_at, 'isoformat'):
                            # It's a datetime object, convert to ISO string first
                            ends_at_iso = ends_at.isoformat()
                            ends_at_str = client.to_local_time(ends_at_iso)
                        else:
                            ends_at_str = str(ends_at)
                    
                    output_results.append({
                        'row': row_num,
                        'listing': item['listing_number'],
                        'max_bid': f"{item['max_bid']:.2f}",
                        'result': 'Added',
                        'auction_id': str(server_result['auction_id']),
                        'ends_at': ends_at_str,
                        'url': server_result.get('listing_url', '-'),
                        'reason': '-'
                    })
                else:
                    # Error from server
                    error_msg = server_result.get('error_message', 'Unknown error') if server_result else 'Item not processed'
                    output_results.append({
                        'row': row_num,
                        'listing': item['listing_number'],
                        'max_bid': f"{item['max_bid']:.2f}",
                        'result': 'Error',
                        'auction_id': '-',
                        'ends_at': '-',
                        'url': '-',
                        'reason': error_msg
                    })
        
        # Calculate summary
        processed_count = len(output_results)
        added_count = sum(1 for r in output_results if r['result'] == 'Added')
        error_count = sum(1 for r in output_results if r['result'] == 'Error')
        duplicate_count = sum(1 for r in output_results if r['result'] == 'Duplicate')
        
        # Print summary
        click.echo(f"Processed: {processed_count}  Added: {added_count}  Errors: {error_count}  Duplicates: {duplicate_count}\n")
        
        # Print table
        if output_results:
            headers = ["Row", "Listing", "MaxBid", "Result", "AuctionID", "Ends At (Local)", "URL", "Reason"]
            
            # Calculate column widths
            col_widths = []
            for i, header in enumerate(headers):
                max_width = len(header)
                for result in output_results:
                    value = str(result.get(header.lower().replace(' ', '_').replace('(', '').replace(')', ''), ''))
                    if header == "Row":
                        value = str(result['row'])
                    elif header == "Listing":
                        value = result['listing']
                    elif header == "MaxBid":
                        value = result['max_bid']
                    elif header == "Result":
                        value = result['result']
                    elif header == "AuctionID":
                        value = result['auction_id']
                    elif header == "Ends At (Local)":
                        value = result['ends_at']
                    elif header == "URL":
                        value = result['url']
                    elif header == "Reason":
                        value = result['reason']
                    max_width = max(max_width, len(value))
                col_widths.append(max(max_width, 8))  # Minimum width of 8
            
            # Build table borders
            def build_separator(left, middle, right, widths):
                return left + middle.join("─" * (w + 2) for w in widths) + right
            
            top_border = build_separator("┌", "┬", "┐", col_widths)
            bottom_border = build_separator("└", "┴", "┘", col_widths)
            header_separator = build_separator("├", "┼", "┤", col_widths)
            
            # Print table
            click.echo(top_border)
            header_row = "│ " + " │ ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers))) + " │"
            click.echo(header_row)
            click.echo(header_separator)
            
            for result in output_results:
                row_data = [
                    str(result['row']),
                    result['listing'],
                    result['max_bid'],
                    result['result'],
                    result['auction_id'],
                    result['ends_at'],
                    result['url'],
                    result['reason']
                ]
                data_row = "│ " + " │ ".join(f"{row_data[i]:<{col_widths[i]}}" for i in range(len(row_data))) + " │"
                click.echo(data_row)
            
            click.echo(bottom_border)
        
    except KeyboardInterrupt:
        click.echo("\nCancelled.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Failed to bulk add listings: {e}", err=True)
        sys.exit(1)


@cli.command()
def list():
    """List all listings."""
    try:
        client = SniperClient()
        all_listings = client.list_snipers()
        
        # Filter listings into active and inactive
        today = datetime.utcnow().date()
        active_listings = []
        inactive_listings = []
        
        for listing in all_listings:
            status = listing['status']
            
            # Active listings: Scheduled, Executing, and BidPlaced
            if status in ["Scheduled", "Executing", "BidPlaced"]:
                active_listings.append(listing)
            # Inactive listings: Failed, Cancelled, or Skipped (if within 7 days)
            elif status in ["Failed", "Cancelled", "Skipped"]:
                # Parse the auction_end_time_utc string to datetime
                ends_at_utc = datetime.fromisoformat(listing['auction_end_time_utc'].replace("Z", "+00:00"))
                ends_at_date = ends_at_utc.date()
                
                # Check if within 7 days of today (can be past or future)
                days_diff = abs((ends_at_date - today).days)
                if days_diff <= 7:
                    inactive_listings.append(listing)
        
        # Helper function to build table rows from listings
        def build_table_rows(listings):
            rows = []
            for listing in listings:
                # Format time remaining until auction ends
                time_remaining = client.time_until_auction_end(listing['auction_end_time_utc'])
                
                # Convert prices to float for formatting (API returns as string)
                current_price = float(listing['current_price']) if isinstance(listing['current_price'], str) else listing['current_price']
                max_bid = float(listing['max_bid']) if isinstance(listing['max_bid'], str) else listing['max_bid']
                
                current_bid_str = f"${current_price:.2f}"
                max_bid_str = f"${max_bid:.2f}"
                # Add asterisk if max bid is lower than current bid
                if max_bid < current_price:
                    max_bid_str += " *"
                
                # Truncate item title to 48 characters
                item_title = listing['item_title']
                if len(item_title) > 48:
                    item_title = item_title[:45] + "..."
                
                url = listing['listing_url']
                
                rows.append((
                    str(listing['id']),
                    listing['status'],
                    current_bid_str,
                    max_bid_str,
                    time_remaining,
                    item_title,
                    url
                ))
            return rows
        
        # Helper function to print a table
        def print_table(title, listings, show_summary=False):
            if not listings:
                return
            
            # Sort by Ends At (auction_end_time_utc) - ascending (earliest first)
            sorted_listings = sorted(
                listings,
                key=lambda x: datetime.fromisoformat(x['auction_end_time_utc'].replace("Z", "+00:00"))
            )
            table_rows = build_table_rows(sorted_listings)
            
            # Calculate column widths
            headers = ["ID", "Status", "Current", "Max", "End", "Item", "URL"]
            col_widths = [max(len(str(row[i])) for row in table_rows) if table_rows else 0 for i in range(len(headers))]
            col_widths = [max(col_widths[i], len(headers[i])) for i in range(len(headers))]
            
            # Set minimum widths based on header length and typical content
            # ID: 2 chars header, but IDs can be multi-digit (min 4)
            # Status: 6 chars header, but "Scheduled"/"Executing" are 9 chars (min 10)
            # Current: 7 chars header, content is "$XXX.XX" up to 7 chars (min 8)
            # Max: 3 chars header, content is "$XXX.XX *" up to 9 chars (min 9)
            # End: 3 chars header, content is "45m"/"5h"/"3d"/"Ended" up to 5 chars (min 6)
            # Item: 4 chars header, content truncated to 48 chars (min 30)
            # URL: 3 chars header, full URLs can be long (min 30)
            min_widths = [4, 10, 8, 9, 6, 30, 30]
            col_widths = [max(col_widths[i], min_widths[i]) for i in range(len(headers))]
            
            # Build table borders
            def build_separator(left, middle, right, widths):
                return left + middle.join("─" * (w + 2) for w in widths) + right
            
            top_border = build_separator("┌", "┬", "┐", col_widths)
            bottom_border = build_separator("└", "┴", "┘", col_widths)
            header_separator = build_separator("├", "┼", "┤", col_widths)
            summary_separator = build_separator("├", "┼", "┤", col_widths)
            
            # Print title
            click.echo(f"\n{title}")
            
            # Print table
            click.echo(top_border)
            # Print header
            header_row = "│ " + " │ ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers))) + " │"
            click.echo(header_row)
            click.echo(header_separator)
            
            # Print data rows
            for row in table_rows:
                data_row = "│ " + " │ ".join(f"{str(row[i]):<{col_widths[i]}}" for i in range(len(row))) + " │"
                click.echo(data_row)
            
            # Add summary row for Active Listings
            if show_summary:
                click.echo(summary_separator)
                # Calculate totals
                total_count = len(sorted_listings)
                total_current = sum(
                    float(listing['current_price']) if isinstance(listing['current_price'], str) 
                    else listing['current_price'] 
                    for listing in sorted_listings
                )
                total_max = sum(
                    float(listing['max_bid']) if isinstance(listing['max_bid'], str) 
                    else listing['max_bid'] 
                    for listing in sorted_listings
                )
                
                summary_row_data = [
                    f"{total_count}",
                    "",
                    f"${total_current:.2f}",
                    f"${total_max:.2f}",
                    "",
                    "",
                    ""
                ]
                summary_row = "│ " + " │ ".join(f"{summary_row_data[i]:<{col_widths[i]}}" for i in range(len(headers))) + " │"
                click.echo(summary_row)
            
            click.echo(bottom_border)
        
        # Print both tables
        if not active_listings and not inactive_listings:
            click.echo("No listings found.")
            return
        
        # Print active listings first (with summary)
        print_table("Active Listings", active_listings, show_summary=True)
        
        # Print inactive listings
        print_table("Inactive Listings", inactive_listings)
    except Exception as e:
        click.echo(f"Failed to list listings: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def show(auction_id):
    """Show detailed information for a listing."""
    try:
        client = SniperClient()
        listing = client.get_status(auction_id)
        
        # Prepare data for table
        max_bid = float(listing['max_bid']) if isinstance(listing['max_bid'], str) else listing['max_bid']
        current_price = float(listing['current_price']) if isinstance(listing['current_price'], str) else listing['current_price']
        final_price = listing.get('final_price')
        final_price_str = "N/A"
        if final_price is not None:
            final_price_float = float(final_price) if isinstance(final_price, str) else final_price
            final_price_str = f"${final_price_float:.2f}"
        
        outcome = listing.get('outcome', 'Pending')
        last_refresh = listing.get('last_price_refresh_utc')
        last_refresh_str = client.to_local_time(last_refresh) if last_refresh else "Never"
        
        # Build table data
        rows = [
            ("ID", str(listing['id'])),
            ("Status", listing['status']),
            ("Item", listing['item_title']),
            ("Listing Number", listing['listing_number']),
            ("Seller", listing.get('seller_name', 'N/A')),
            ("URL", listing['listing_url']),
            ("Current Price", f"${current_price:.2f}"),
            ("Max Bid", f"${max_bid:.2f}"),
            ("Currency", listing.get('currency', 'USD')),
            ("Ends At", client.to_local_time(listing['auction_end_time_utc'])),
            ("Outcome", outcome),
            ("Final Price", final_price_str),
        ]
        
        # Add skip reason if applicable
        if listing['status'] == 'Skipped' and listing.get('skip_reason'):
            rows.append(("Skip Reason", listing['skip_reason']))
        
        rows.append(("Last Price Refresh", last_refresh_str))
        
        # Calculate column widths
        label_width = max(len(row[0]) for row in rows)
        value_width = max(len(row[1]) for row in rows)
        
        # Ensure minimum widths
        label_width = max(label_width, 20)
        value_width = max(value_width, 50)
        
        # Print table
        top_border = "┌" + "─" * (label_width + 2) + "┬" + "─" * (value_width + 2) + "┐"
        bottom_border = "└" + "─" * (label_width + 2) + "┴" + "─" * (value_width + 2) + "┘"
        separator = "├" + "─" * (label_width + 2) + "┼" + "─" * (value_width + 2) + "┤"
        
        click.echo(top_border)
        click.echo(f"│ {('Field'):<{label_width}} │ {('Value'):<{value_width}} │")
        click.echo(separator)
        
        for label, value in rows:
            # Handle long values by wrapping (especially URLs and long item titles)
            if len(value) > value_width:
                # Split long values into multiple lines
                # If value contains spaces, wrap by words; otherwise wrap by characters
                if ' ' in value:
                    # Wrap by words
                    words = value.split(' ')
                    lines = []
                    current_line = ""
                    for word in words:
                        test_line = current_line + (" " if current_line else "") + word
                        if len(test_line) <= value_width:
                            current_line = test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = word
                    if current_line:
                        lines.append(current_line)
                else:
                    # Wrap by characters (for URLs without spaces)
                    lines = []
                    for i in range(0, len(value), value_width):
                        lines.append(value[i:i + value_width])
                
                # Print wrapped lines
                for i, line in enumerate(lines):
                    label_display = label if i == 0 else ""
                    click.echo(f"│ {label_display:<{label_width}} │ {line:<{value_width}} │")
            else:
                click.echo(f"│ {label:<{label_width}} │ {value:<{value_width}} │")
        
        click.echo(bottom_border)
    except Exception as e:
        click.echo(f"Failed to show listing: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def status(auction_id):
    """Get status of a listing."""
    try:
        client = SniperClient()
        listing = client.get_status(auction_id)
        
        click.echo(f"Status: {listing['status']}")
        
        if listing['status'] == 'Skipped' and listing.get('skip_reason'):
            click.echo(f"Reason: {listing['skip_reason']}")
            current_price = float(listing['current_price']) if isinstance(listing['current_price'], str) else listing['current_price']
            click.echo(f"Price at Check: ${current_price:.2f}")
        else:
            click.echo(f"Item: {listing['item_title']}")
            max_bid = float(listing['max_bid']) if isinstance(listing['max_bid'], str) else listing['max_bid']
            current_price = float(listing['current_price']) if isinstance(listing['current_price'], str) else listing['current_price']
            click.echo(f"Max bid: ${max_bid:.2f}")
            click.echo(f"Current price: ${current_price:.2f}")
            click.echo(f"Ends at: {client.to_local_time(listing['auction_end_time_utc'])}")
            
            # Show outcome and final price if available
            outcome = listing.get('outcome')
            if outcome and outcome != 'Pending':
                click.echo(f"Outcome: {outcome}")
                final_price = listing.get('final_price')
                if final_price:
                    final_price_float = float(final_price) if isinstance(final_price, str) else final_price
                    click.echo(f"Final price: ${final_price_float:.2f}")
            
            click.echo(f"URL: {listing['listing_url']}")
    except Exception as e:
        click.echo(f"Failed to get status: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def remove(auction_id):
    """Remove (cancel) a listing."""
    try:
        client = SniperClient()
        client.remove_sniper(auction_id)
        click.echo(f"Listing {auction_id} cancelled successfully.")
    except Exception as e:
        click.echo(f"Failed to remove listing: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def logs(auction_id):
    """Get bid attempt logs for a listing."""
    try:
        client = SniperClient()
        logs = client.get_logs(auction_id)
        
        if not logs:
            click.echo("No bid attempts recorded for this auction.")
            return
        
        click.echo(f"Bid Attempt for Auction {auction_id}")
        click.echo(f"Attempt time: {client.to_local_time(logs['attempt_time_utc'])}")
        click.echo(f"Result: {logs['result']}")
        if logs.get('error_message'):
            click.echo(f"Error: {logs['error_message']}")
    except Exception as e:
        click.echo(f"Failed to get logs: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

