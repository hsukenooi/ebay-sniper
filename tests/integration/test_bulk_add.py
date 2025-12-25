#!/usr/bin/env python3
"""
Integration tests for bulk add command.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from cli.main import add_bulk
import click
from click.testing import CliRunner
from cli.client import SniperClient


class TestBulkAddCommand:
    """Integration tests for add-bulk command."""
    
    def test_bulk_add_success(self):
        """Test successful bulk add with multiple items."""
        runner = CliRunner()
        
        # Mock server response
        mock_response = {
            'results': [
                {
                    'listing_number': '123456789012',
                    'max_bid': 325.0,
                    'success': True,
                    'auction_id': 1,
                    'item_title': 'Test Item 1',
                    'current_price': 300.0,
                    'auction_end_time_utc': '2025-01-20T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/123456789012'
                },
                {
                    'listing_number': '234567890123',
                    'max_bid': 400.0,
                    'success': True,
                    'auction_id': 2,
                    'item_title': 'Test Item 2',
                    'current_price': 350.0,
                    'auction_end_time_utc': '2025-01-21T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/234567890123'
                }
            ]
        }
        
        input_data = "123456789012 325\n234567890123 400\n"
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            with patch.object(SniperClient, 'to_local_time', side_effect=lambda x: '2025-01-20 10:00:00' if '2025-01-20' in x else '2025-01-21 10:00:00'):
                result = runner.invoke(add_bulk, input=input_data)
                
                assert result.exit_code == 0
                assert "Processed: 2" in result.output
                assert "Added: 2" in result.output
                assert "Errors: 0" in result.output
                assert "123456789012" in result.output
                assert "234567890123" in result.output
    
    def test_bulk_add_with_duplicates(self):
        """Test bulk add with duplicate listing numbers in input."""
        runner = CliRunner()
        
        mock_response = {
            'results': [
                {
                    'listing_number': '123456789012',
                    'max_bid': 325.0,
                    'success': True,
                    'auction_id': 1,
                    'item_title': 'Test Item',
                    'current_price': 300.0,
                    'auction_end_time_utc': '2025-01-20T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/123456789012'
                }
            ]
        }
        
        input_data = "123456789012 325\n123456789012 400\n"  # Duplicate
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            with patch.object(SniperClient, 'to_local_time', return_value='2025-01-20 10:00:00'):
                result = runner.invoke(add_bulk, input=input_data)
                
                assert result.exit_code == 0
                assert "Processed: 2" in result.output
                assert "Duplicates: 1" in result.output
                assert "Duplicate" in result.output
    
    def test_bulk_add_with_errors(self):
        """Test bulk add with server errors."""
        runner = CliRunner()
        
        mock_response = {
            'results': [
                {
                    'listing_number': '123456789012',
                    'max_bid': 325.0,
                    'success': True,
                    'auction_id': 1,
                    'item_title': 'Test Item',
                    'current_price': 300.0,
                    'auction_end_time_utc': '2025-01-20T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/123456789012'
                },
                {
                    'listing_number': '999999999999',
                    'max_bid': 50.0,
                    'success': False,
                    'error_message': 'Listing not found'
                }
            ]
        }
        
        input_data = "123456789012 325\n999999999999 50\n"
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            with patch.object(SniperClient, 'to_local_time', return_value='2025-01-20 10:00:00'):
                result = runner.invoke(add_bulk, input=input_data)
                
                assert result.exit_code == 0
                assert "Processed: 2" in result.output
                assert "Added: 1" in result.output
                assert "Errors: 1" in result.output
                assert "Error" in result.output
                assert "Listing not found" in result.output
    
    def test_bulk_add_with_invalid_format(self):
        """Test bulk add with invalid input format."""
        runner = CliRunner()
        
        mock_response = {'results': []}
        
        input_data = "invalid text\n123456789012\n"  # Invalid formats
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            result = runner.invoke(add_bulk, input=input_data)
            
            assert result.exit_code == 0
            assert "Errors: 2" in result.output or "Error" in result.output
    
    def test_bulk_add_ignores_comments_and_blanks(self):
        """Test that comments and blank lines are ignored."""
        runner = CliRunner()
        
        mock_response = {
            'results': [
                {
                    'listing_number': '123456789012',
                    'max_bid': 325.0,
                    'success': True,
                    'auction_id': 1,
                    'item_title': 'Test Item',
                    'current_price': 300.0,
                    'auction_end_time_utc': '2025-01-20T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/123456789012'
                }
            ]
        }
        
        input_data = "# Comment line\n123456789012 325\n\n# Another comment\n"
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            with patch.object(SniperClient, 'to_local_time', return_value='2025-01-20 10:00:00'):
                result = runner.invoke(add_bulk, input=input_data)
                
                assert result.exit_code == 0
                assert "Processed: 1" in result.output
                assert "Added: 1" in result.output
    
    def test_bulk_add_multiple_formats(self):
        """Test bulk add with multiple input formats."""
        runner = CliRunner()
        
        mock_response = {
            'results': [
                {
                    'listing_number': '123456789012',
                    'max_bid': 325.0,
                    'success': True,
                    'auction_id': 1,
                    'item_title': 'Test Item',
                    'current_price': 300.0,
                    'auction_end_time_utc': '2025-01-20T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/123456789012'
                },
                {
                    'listing_number': '234567890123',
                    'max_bid': 400.0,
                    'success': True,
                    'auction_id': 2,
                    'item_title': 'Test Item 2',
                    'current_price': 350.0,
                    'auction_end_time_utc': '2025-01-21T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/234567890123'
                },
                {
                    'listing_number': '345678901234',
                    'max_bid': 500.0,
                    'success': True,
                    'auction_id': 3,
                    'item_title': 'Test Item 3',
                    'current_price': 450.0,
                    'auction_end_time_utc': '2025-01-22T10:00:00',
                    'listing_url': 'https://www.ebay.com/itm/345678901234'
                }
            ]
        }
        
        input_data = "123456789012 325\n234567890123,400\n345678901234\t500\n"
        
        with patch.object(SniperClient, 'bulk_add_snipers', return_value=mock_response):
            with patch.object(SniperClient, 'to_local_time', side_effect=lambda x: '2025-01-20 10:00:00' if '2025-01-20' in x else ('2025-01-21 10:00:00' if '2025-01-21' in x else '2025-01-22 10:00:00')):
                result = runner.invoke(add_bulk, input=input_data)
                
                assert result.exit_code == 0
                assert "Processed: 3" in result.output
                assert "Added: 3" in result.output
                assert "123456789012" in result.output
                assert "234567890123" in result.output
                assert "345678901234" in result.output

