#!/usr/bin/env python3
import click
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from .client import SniperClient
from .config import save_token, get_timezone, save_timezone
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
    """Add a new sniper for an auction."""
    try:
        max_bid_decimal = Decimal(max_bid.replace("$", "").replace(",", ""))
        client = SniperClient()
        result = client.add_sniper(listing_number, max_bid_decimal)
        click.echo(f"Sniper added for auction {result['id']}")
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
        click.echo(f"Failed to add sniper: {e}", err=True)
        sys.exit(1)


@cli.command()
def list():
    """List all snipers."""
    try:
        client = SniperClient()
        all_snipers = client.list_snipers()
        
        # Filter snipers based on status and date
        today = datetime.utcnow().date()
        filtered_snipers = []
        
        for sniper in all_snipers:
            status = sniper['status']
            
            # Always show Scheduled items
            if status == "Scheduled":
                filtered_snipers.append(sniper)
            # Show Failed or Cancelled items if Ends At is within a week of today
            elif status in ["Failed", "Cancelled"]:
                # Parse the auction_end_time_utc string to datetime
                ends_at_utc = datetime.fromisoformat(sniper['auction_end_time_utc'].replace("Z", "+00:00"))
                ends_at_date = ends_at_utc.date()
                
                # Check if within 7 days of today (can be past or future)
                days_diff = abs((ends_at_date - today).days)
                if days_diff <= 7:
                    filtered_snipers.append(sniper)
        
        if not filtered_snipers:
            click.echo("No snipers found.")
            return
        
        # Sort by Ends At (auction_end_time_utc) - ascending (earliest first)
        filtered_snipers = sorted(
            filtered_snipers, 
            key=lambda x: datetime.fromisoformat(x['auction_end_time_utc'].replace("Z", "+00:00"))
        )
        
        # Print header: ID, Status, Current Bid, Max Bid, Ends At, Item, URL
        click.echo(f"{'ID':<4}  {'Status':<12}  {'Current Bid':<12}  {'Max Bid':<10}  {'Ends At':<12}  {'Item':<48}  {'URL':<40}")
        click.echo("-" * 140)
        
        # Print rows
        for sniper in filtered_snipers:
            # Format time without seconds and without year
            ends_at_local = client.to_local_time_no_year(sniper['auction_end_time_utc'])
            
            # Convert prices to float for formatting (API returns as string)
            current_price = float(sniper['current_price']) if isinstance(sniper['current_price'], str) else sniper['current_price']
            max_bid = float(sniper['max_bid']) if isinstance(sniper['max_bid'], str) else sniper['max_bid']
            
            current_bid_str = f"${current_price:.2f}"
            max_bid_str = f"${max_bid:.2f}"
            
            # Truncate item title to 48 characters
            item_title = sniper['item_title']
            if len(item_title) > 48:
                item_title = item_title[:45] + "..."
            
            url = sniper['listing_url']
            
            click.echo(
                f"{sniper['id']:<4}  {sniper['status']:<12}  {current_bid_str:<12}  {max_bid_str:<10}  "
                f"{ends_at_local:<12}  {item_title:<48}  {url:<40}"
            )
    except Exception as e:
        click.echo(f"Failed to list snipers: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def status(auction_id):
    """Get status of a sniper."""
    try:
        client = SniperClient()
        sniper = client.get_status(auction_id)
        
        click.echo(f"Status: {sniper['status']}")
        
        if sniper['status'] == 'Skipped' and sniper.get('skip_reason'):
            click.echo(f"Reason: {sniper['skip_reason']}")
            current_price = float(sniper['current_price']) if isinstance(sniper['current_price'], str) else sniper['current_price']
            click.echo(f"Price at Check: ${current_price:.2f}")
        else:
            click.echo(f"Item: {sniper['item_title']}")
            max_bid = float(sniper['max_bid']) if isinstance(sniper['max_bid'], str) else sniper['max_bid']
            current_price = float(sniper['current_price']) if isinstance(sniper['current_price'], str) else sniper['current_price']
            click.echo(f"Max bid: ${max_bid:.2f}")
            click.echo(f"Current price: ${current_price:.2f}")
            click.echo(f"Ends at: {client.to_local_time(sniper['auction_end_time_utc'])}")
            click.echo(f"URL: {sniper['listing_url']}")
    except Exception as e:
        click.echo(f"Failed to get status: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def remove(auction_id):
    """Remove (cancel) a sniper."""
    try:
        client = SniperClient()
        client.remove_sniper(auction_id)
        click.echo(f"Sniper {auction_id} cancelled successfully.")
    except Exception as e:
        click.echo(f"Failed to remove sniper: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("auction_id", type=int)
def logs(auction_id):
    """Get bid attempt logs for a sniper."""
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

