#!/usr/bin/env python3
import click
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from .client import SniperClient
from .config import save_token, get_timezone
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


@cli.command()
def list():
    """List all listings."""
    try:
        client = SniperClient()
        all_listings = client.list_snipers()
        
        # Filter listings based on status and date
        today = datetime.utcnow().date()
        filtered_listings = []
        
        for listing in all_listings:
            status = listing['status']
            
            # Always show Scheduled, Executing, and BidPlaced items
            if status in ["Scheduled", "Executing", "BidPlaced"]:
                filtered_listings.append(listing)
            # Show Failed, Cancelled, or Skipped items if Ends At is within a week of today
            elif status in ["Failed", "Cancelled", "Skipped"]:
                # Parse the auction_end_time_utc string to datetime
                ends_at_utc = datetime.fromisoformat(listing['auction_end_time_utc'].replace("Z", "+00:00"))
                ends_at_date = ends_at_utc.date()
                
                # Check if within 7 days of today (can be past or future)
                days_diff = abs((ends_at_date - today).days)
                if days_diff <= 7:
                    filtered_listings.append(listing)
        
        if not filtered_listings:
            click.echo("No listings found.")
            return
        
        # Sort by Ends At (auction_end_time_utc) - ascending (earliest first)
        filtered_listings = sorted(
            filtered_listings, 
            key=lambda x: datetime.fromisoformat(x['auction_end_time_utc'].replace("Z", "+00:00"))
        )
        
        # Print header: ID, Status, Current Bid, Max Bid, Time Left, Item, URL
        click.echo(f"{'ID':<4}  {'Status':<12}  {'Current Bid':<12}  {'Max Bid':<10}  {'Time Left':<12}  {'Item':<48}  {'URL':<40}")
        click.echo("-" * 130)
        
        # Print rows
        for listing in filtered_listings:
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
            
            click.echo(
                f"{listing['id']:<4}  {listing['status']:<12}  {current_bid_str:<12}  {max_bid_str:<10}  "
                f"{time_remaining:<12}  {item_title:<48}  {url:<40}"
            )
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

