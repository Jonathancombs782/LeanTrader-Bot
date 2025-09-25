"""
Notification Manager for Trading Bot
Multi-channel notifications via Telegram, Email, SMS, and Webhooks
"""

import asyncio
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger
import json

class NotificationManager:
    """Advanced notification system for trading bot alerts"""
    
    def __init__(self):
        # Notification channels
        self.telegram_enabled = False
        self.email_enabled = False
        self.sms_enabled = False
        self.webhook_enabled = False
        
        # Configuration
        self.config = {
            'telegram': {
                'bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
                'chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
                'enabled': False
            },
            'email': {
                'smtp_server': os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('EMAIL_PORT', 587)),
                'username': os.getenv('EMAIL_USER', ''),
                'password': os.getenv('EMAIL_PASSWORD', ''),
                'recipient': os.getenv('EMAIL_RECIPIENT', ''),
                'enabled': False
            },
            'sms': {
                'account_sid': os.getenv('TWILIO_ACCOUNT_SID', ''),
                'auth_token': os.getenv('TWILIO_AUTH_TOKEN', ''),
                'from_number': os.getenv('TWILIO_FROM_NUMBER', ''),
                'to_number': os.getenv('TWILIO_TO_NUMBER', ''),
                'enabled': False
            },
            'webhook': {
                'url': os.getenv('WEBHOOK_URL', ''),
                'enabled': False
            }
        }
        
        # Alert levels
        self.alert_levels = {
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨',
            'SUCCESS': '✅'
        }
        
        # Rate limiting
        self.rate_limits = {
            'telegram': {'last_sent': None, 'min_interval': 1},  # 1 second
            'email': {'last_sent': None, 'min_interval': 60},    # 1 minute
            'sms': {'last_sent': None, 'min_interval': 300},     # 5 minutes
            'webhook': {'last_sent': None, 'min_interval': 5}    # 5 seconds
        }
        
    async def initialize(self):
        """Initialize notification manager"""
        logger.info("📱 Initializing Notification Manager...")
        
        try:
            # Check and enable available channels
            await self._check_telegram_config()
            await self._check_email_config()
            await self._check_sms_config()
            await self._check_webhook_config()
            
            logger.info("✅ Notification Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize notification manager: {e}")
            raise
            
    async def _check_telegram_config(self):
        """Check Telegram configuration"""
        if self.config['telegram']['bot_token'] and self.config['telegram']['chat_id']:
            try:
                # Test Telegram connection
                url = f"https://api.telegram.org/bot{self.config['telegram']['bot_token']}/getMe"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    self.telegram_enabled = True
                    self.config['telegram']['enabled'] = True
                    logger.info("✅ Telegram notifications enabled")
                else:
                    logger.warning("⚠️ Telegram configuration invalid")
                    
            except Exception as e:
                logger.warning(f"⚠️ Telegram connection failed: {e}")
                
    async def _check_email_config(self):
        """Check email configuration"""
        if (self.config['email']['username'] and 
            self.config['email']['password'] and 
            self.config['email']['recipient']):
            try:
                # Test email connection
                server = smtplib.SMTP(self.config['email']['smtp_server'], self.config['email']['smtp_port'])
                server.starttls()
                server.login(self.config['email']['username'], self.config['email']['password'])
                server.quit()
                
                self.email_enabled = True
                self.config['email']['enabled'] = True
                logger.info("✅ Email notifications enabled")
                
            except Exception as e:
                logger.warning(f"⚠️ Email configuration failed: {e}")
                
    async def _check_sms_config(self):
        """Check SMS configuration"""
        if (self.config['sms']['account_sid'] and 
            self.config['sms']['auth_token'] and 
            self.config['sms']['from_number'] and 
            self.config['sms']['to_number']):
            try:
                # Test Twilio connection
                from twilio.rest import Client
                client = Client(self.config['sms']['account_sid'], self.config['sms']['auth_token'])
                
                # Just verify credentials, don't send a test message
                account = client.api.accounts(self.config['sms']['account_sid']).fetch()
                
                self.sms_enabled = True
                self.config['sms']['enabled'] = True
                logger.info("✅ SMS notifications enabled")
                
            except Exception as e:
                logger.warning(f"⚠️ SMS configuration failed: {e}")
                
    async def _check_webhook_config(self):
        """Check webhook configuration"""
        if self.config['webhook']['url']:
            try:
                # Test webhook URL
                test_payload = {'test': True, 'timestamp': datetime.now().isoformat()}
                response = requests.post(self.config['webhook']['url'], json=test_payload, timeout=10)
                
                if response.status_code in [200, 201, 202]:
                    self.webhook_enabled = True
                    self.config['webhook']['enabled'] = True
                    logger.info("✅ Webhook notifications enabled")
                else:
                    logger.warning(f"⚠️ Webhook returned status {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Webhook configuration failed: {e}")
                
    async def send_notification(self, title: str, message: str, level: str = 'INFO', channels: List[str] = None):
        """Send notification through enabled channels"""
        try:
            if channels is None:
                channels = ['telegram', 'email', 'webhook']  # Default channels
                
            # Format message with emoji
            emoji = self.alert_levels.get(level, 'ℹ️')
            formatted_title = f"{emoji} {title}"
            formatted_message = f"{formatted_title}\n\n{message}\n\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Send through each channel
            tasks = []
            
            if 'telegram' in channels and self.telegram_enabled:
                tasks.append(self._send_telegram(formatted_title, message))
                
            if 'email' in channels and self.email_enabled:
                tasks.append(self._send_email(formatted_title, message))
                
            if 'sms' in channels and self.sms_enabled and level in ['ERROR', 'CRITICAL']:
                tasks.append(self._send_sms(formatted_title, message))
                
            if 'webhook' in channels and self.webhook_enabled:
                tasks.append(self._send_webhook(title, message, level))
                
            # Execute all notifications concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"📤 Sent {level} notification: {title}")
            else:
                logger.warning(f"⚠️ No notification channels available for: {title}")
                
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            
    async def _send_telegram(self, title: str, message: str):
        """Send Telegram notification"""
        try:
            if not self._check_rate_limit('telegram'):
                return
                
            url = f"https://api.telegram.org/bot{self.config['telegram']['bot_token']}/sendMessage"
            
            payload = {
                'chat_id': self.config['telegram']['chat_id'],
                'text': f"{title}\n\n{message}",
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.rate_limits['telegram']['last_sent'] = datetime.now()
                logger.debug("📱 Telegram notification sent")
            else:
                logger.error(f"Telegram API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            
    async def _send_email(self, title: str, message: str):
        """Send email notification"""
        try:
            if not self._check_rate_limit('email'):
                return
                
            msg = MIMEMultipart()
            msg['From'] = self.config['email']['username']
            msg['To'] = self.config['email']['recipient']
            msg['Subject'] = f"Trading Bot Alert: {title}"
            
            body = f"""
            {title}
            
            {message}
            
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            ---
            Trading Bot Notification System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config['email']['smtp_server'], self.config['email']['smtp_port'])
            server.starttls()
            server.login(self.config['email']['username'], self.config['email']['password'])
            text = msg.as_string()
            server.sendmail(self.config['email']['username'], self.config['email']['recipient'], text)
            server.quit()
            
            self.rate_limits['email']['last_sent'] = datetime.now()
            logger.debug("📧 Email notification sent")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            
    async def _send_sms(self, title: str, message: str):
        """Send SMS notification"""
        try:
            if not self._check_rate_limit('sms'):
                return
                
            from twilio.rest import Client
            
            client = Client(self.config['sms']['account_sid'], self.config['sms']['auth_token'])
            
            # Truncate message for SMS (160 char limit)
            sms_message = f"{title}: {message}"[:160]
            
            message_obj = client.messages.create(
                body=sms_message,
                from_=self.config['sms']['from_number'],
                to=self.config['sms']['to_number']
            )
            
            self.rate_limits['sms']['last_sent'] = datetime.now()
            logger.debug(f"📱 SMS notification sent: {message_obj.sid}")
            
        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}")
            
    async def _send_webhook(self, title: str, message: str, level: str):
        """Send webhook notification"""
        try:
            if not self._check_rate_limit('webhook'):
                return
                
            payload = {
                'title': title,
                'message': message,
                'level': level,
                'timestamp': datetime.now().isoformat(),
                'source': 'trading_bot'
            }
            
            response = requests.post(
                self.config['webhook']['url'], 
                json=payload, 
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code in [200, 201, 202]:
                self.rate_limits['webhook']['last_sent'] = datetime.now()
                logger.debug("🔗 Webhook notification sent")
            else:
                logger.error(f"Webhook error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            
    def _check_rate_limit(self, channel: str) -> bool:
        """Check if channel is within rate limits"""
        try:
            rate_limit = self.rate_limits.get(channel)
            if not rate_limit:
                return True
                
            last_sent = rate_limit['last_sent']
            min_interval = rate_limit['min_interval']
            
            if last_sent is None:
                return True
                
            time_since_last = (datetime.now() - last_sent).total_seconds()
            return time_since_last >= min_interval
            
        except Exception as e:
            logger.error(f"Error checking rate limit for {channel}: {e}")
            return True
            
    async def send_trade_alert(self, trade_data: Dict):
        """Send trade execution alert"""
        try:
            symbol = trade_data.get('symbol', 'Unknown')
            action = trade_data.get('action', 'Unknown')
            price = trade_data.get('price', 0)
            quantity = trade_data.get('quantity', 0)
            confidence = trade_data.get('confidence', 0)
            reasoning = trade_data.get('reasoning', 'No reasoning provided')
            
            title = f"Trade Executed: {action} {symbol}"
            message = f"""
            <b>Symbol:</b> {symbol}
            <b>Action:</b> {action}
            <b>Price:</b> ${price:.4f}
            <b>Quantity:</b> {quantity:.6f}
            <b>Confidence:</b> {confidence:.2%}
            <b>Reasoning:</b> {reasoning}
            """
            
            await self.send_notification(title, message, 'INFO')
            
        except Exception as e:
            logger.error(f"Error sending trade alert: {e}")
            
    async def send_performance_alert(self, performance_data: Dict):
        """Send performance summary alert"""
        try:
            total_return = performance_data.get('total_return_pct', 0)
            win_rate = performance_data.get('win_rate', 0)
            total_trades = performance_data.get('total_trades', 0)
            current_value = performance_data.get('current_portfolio_value', 0)
            
            title = "Daily Performance Summary"
            message = f"""
            <b>Portfolio Value:</b> ${current_value:,.2f}
            <b>Total Return:</b> {total_return:.2f}%
            <b>Win Rate:</b> {win_rate:.1f}%
            <b>Total Trades:</b> {total_trades}
            """
            
            # Determine alert level based on performance
            level = 'SUCCESS' if total_return > 0 else 'WARNING'
            
            await self.send_notification(title, message, level)
            
        except Exception as e:
            logger.error(f"Error sending performance alert: {e}")
            
    async def send_risk_alert(self, risk_data: Dict):
        """Send risk management alert"""
        try:
            exposure = risk_data.get('total_exposure', 0)
            drawdown = risk_data.get('max_drawdown', 0)
            var = risk_data.get('var_95', 0)
            
            title = "Risk Management Alert"
            message = f"""
            <b>Total Exposure:</b> {exposure:.2%}
            <b>Max Drawdown:</b> {drawdown:.2%}
            <b>Value at Risk (95%):</b> {var:.2%}
            """
            
            # Determine alert level based on risk metrics
            if drawdown > 0.1 or exposure > 0.8:
                level = 'CRITICAL'
            elif drawdown > 0.05 or exposure > 0.6:
                level = 'ERROR'
            else:
                level = 'WARNING'
                
            await self.send_notification(title, message, level)
            
        except Exception as e:
            logger.error(f"Error sending risk alert: {e}")
            
    async def send_system_alert(self, system_data: Dict):
        """Send system status alert"""
        try:
            status = system_data.get('status', 'Unknown')
            error_count = system_data.get('error_count', 0)
            positions_count = system_data.get('positions_count', 0)
            
            title = f"System Status: {status}"
            message = f"""
            <b>Status:</b> {status}
            <b>Open Positions:</b> {positions_count}
            <b>Error Count:</b> {error_count}
            """
            
            # Determine alert level
            if status == 'ERROR' or error_count > 10:
                level = 'ERROR'
            elif status == 'WARNING' or error_count > 5:
                level = 'WARNING'
            else:
                level = 'INFO'
                
            await self.send_notification(title, message, level)
            
        except Exception as e:
            logger.error(f"Error sending system alert: {e}")
            
    async def get_notification_status(self) -> Dict:
        """Get notification system status"""
        return {
            'channels': {
                'telegram': {
                    'enabled': self.telegram_enabled,
                    'configured': bool(self.config['telegram']['bot_token'] and self.config['telegram']['chat_id'])
                },
                'email': {
                    'enabled': self.email_enabled,
                    'configured': bool(self.config['email']['username'] and self.config['email']['password'])
                },
                'sms': {
                    'enabled': self.sms_enabled,
                    'configured': bool(self.config['sms']['account_sid'] and self.config['sms']['auth_token'])
                },
                'webhook': {
                    'enabled': self.webhook_enabled,
                    'configured': bool(self.config['webhook']['url'])
                }
            },
            'rate_limits': self.rate_limits,
            'alert_levels': list(self.alert_levels.keys())
        }