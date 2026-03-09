import requests
import json
import base64
from datetime import datetime
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class MpesaService:
    """Service class for M-Pesa API interactions"""
    
    def __init__(self):
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.passkey = settings.MPESA_PASSKEY
        self.shortcode = settings.MPESA_SHORTCODE
        self.environment = settings.MPESA_ENVIRONMENT
        
        # Base URLs
        if self.environment == 'production':
            self.base_url = 'https://api.safaricom.co.ke'
        else:
            self.base_url = 'https://sandbox.safaricom.co.ke'
    
    def get_access_token(self):
        """Get OAuth access token from M-Pesa"""
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            response = requests.get(
                url,
                auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret)
            )
            response.raise_for_status()
            result = response.json()
            return result['access_token']
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            raise Exception(f"Failed to get access token: {str(e)}")
    
    def generate_password(self, timestamp):
        """Generate password for STK push"""
        data_to_encode = (
            self.shortcode +
            self.passkey +
            timestamp
        )
        return base64.b64encode(data_to_encode.encode()).decode('utf-8')
    
    def stk_push(self, phone_number, amount, account_reference, transaction_desc, callback_url=None):
        """
        Initiate STK Push to customer's phone
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        # Format phone number (remove 0 or +254, ensure 254...)
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif phone_number.startswith('+'):
            phone_number = phone_number[1:]
        elif not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        
        # Use default callback if none provided
        if not callback_url:
            callback_url = settings.MPESA_CALLBACK_URL
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone_number,
            'PartyB': self.shortcode,
            'PhoneNumber': phone_number,
            'CallBackURL': callback_url,
            'AccountReference': account_reference[:12],  # Max 12 chars
            'TransactionDesc': transaction_desc[:13]  # Max 13 chars
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"STK Push initiated: {result}")
            return result
        except Exception as e:
            logger.error(f"Error initiating STK push: {str(e)}")
            raise Exception(f"STK push failed: {str(e)}")
    
    def query_status(self, checkout_request_id):
        """
        Query the status of an STK push transaction
        """
        access_token = self.get_access_token()
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': checkout_request_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error querying transaction status: {str(e)}")
            raise Exception(f"Status query failed: {str(e)}")