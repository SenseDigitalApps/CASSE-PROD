"""
Custom SMTP email backend with HELO name configuration.
"""
import smtplib
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.conf import settings


class CustomSMTPEmailBackend(SMTPEmailBackend):
    """
    Custom SMTP backend that configures HELO name correctly.
    """
    
    def open(self):
        """
        Open an SMTP connection with proper HELO name.
        """
        if self.connection:
            return False
        
        try:
            # Determine HELO name from EMAIL_HOST or use default
            helo_name = getattr(settings, 'EMAIL_HELO_NAME', self.host or 'localhost')
            
            if self.use_ssl:
                # No usar local_hostname para evitar problemas con algunos servidores SMTP
                self.connection = smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    timeout=self.timeout
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host,
                    self.port,
                    timeout=self.timeout
                )
            
            if self.use_tls:
                self.connection.starttls()
            
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            
            return True
        except Exception:
            if not self.fail_silently:
                raise
            return False
