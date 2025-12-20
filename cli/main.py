#!/usr/bin/env python3
import click
from decimal import Decimal, InvalidOperation
from datetime import datetime
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
        click.echo(f"Max bid: ${result['max_bid']}")
        click.echo(f"Ends at: {client.to_local_time(result['auction_end_time_utc'])}")
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
        snipers = client.list_snipers()
        
        if not snipers:
            click.echo("No snipers found.")
            return
        
        # Print header (matching exact format from requirements)
        click.echo(f"{'ID':<4}  {'Status':<12}  {'Ends At (Local)':<20}  {'Max Bid':<10}  {'URL':<40}  {'Item':<30}")
        click.echo("-" * 120)
        
        # Print rows
        for sniper in snipers:
            ends_at_local = client.to_local_time(sniper['auction_end_time_utc'])
            max_bid_str = f"${sniper['max_bid']:.2f}"
            url = sniper['listing_url']
            item_title = sniper['item_title']
            
            click.echo(
                f"{sniper['id']:<4}  {sniper['status']:<12}  {ends_at_local:<20}  "
                f"{max_bid_str:<10}  {url:<40}  {item_title:<30}"
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
            click.echo(f"Price at Check: ${sniper['current_price']:.2f}")
        else:
            click.echo(f"Item: {sniper['item_title']}")
            click.echo(f"Max bid: ${sniper['max_bid']:.2f}")
            click.echo(f"Current price: ${sniper['current_price']:.2f}")
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

