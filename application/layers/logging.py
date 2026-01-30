"""
Logging Layer for Multi-Tenant SaaS
Provides structured logging with tenant context
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

class TenantLogger:
    """Structured logger with tenant context"""
    
    def __init__(self, tenant_id: str = None, service_name: str = None):
        self.tenant_id = tenant_id
        self.service_name = service_name or os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')
        self.logger = logging.getLogger(self.service_name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Add structured handler
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
    
    def _format_log(self, level: str, message: str, extra: Dict[str, Any] = None) -> str:
        """Format log entry as JSON"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': level,
            'service': self.service_name,
            'message': message
        }
        
        if self.tenant_id:
            log_entry['tenant_id'] = self.tenant_id
        
        if extra:
            log_entry['extra'] = extra
        
        return json.dumps(log_entry)
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(self._format_log('INFO', message, kwargs))
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(self._format_log('WARNING', message, kwargs))
    
    def error(self, message: str, **kwargs):
        """Log error message"""
        self.logger.error(self._format_log('ERROR', message, kwargs))
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(self._format_log('DEBUG', message, kwargs))
    
    def log_request(self, event: Dict[str, Any]):
        """Log API request"""
        self.info('API Request', 
                 http_method=event.get('httpMethod'),
                 path=event.get('path'),
                 source_ip=event.get('requestContext', {}).get('identity', {}).get('sourceIp'))
    
    def log_response(self, status_code: int, duration_ms: float):
        """Log API response"""
        self.info('API Response',
                 status_code=status_code,
                 duration_ms=duration_ms)
    
    def log_database_query(self, query: str, duration_ms: float):
        """Log database query"""
        self.debug('Database Query',
                  query=query[:100],  # Truncate long queries
                  duration_ms=duration_ms)
    
    def log_exception(self, exception: Exception, context: Dict[str, Any] = None):
        """Log exception with context"""
        import traceback
        self.error('Exception occurred',
                  exception_type=type(exception).__name__,
                  exception_message=str(exception),
                  traceback=traceback.format_exc(),
                  context=context)


def get_logger(tenant_id: str = None, service_name: str = None) -> TenantLogger:
    """Get tenant-aware logger instance"""
    return TenantLogger(tenant_id, service_name)


# CloudWatch Insights Query Examples
INSIGHTS_QUERIES = {
    'errors_by_tenant': '''
        fields @timestamp, tenant_id, message
        | filter level = "ERROR"
        | stats count() by tenant_id
        | sort count desc
    ''',
    
    'slow_requests': '''
        fields @timestamp, tenant_id, duration_ms
        | filter duration_ms > 1000
        | sort duration_ms desc
        | limit 20
    ''',
    
    'requests_per_tenant': '''
        fields @timestamp, tenant_id
        | stats count() by tenant_id, bin(5m)
    ''',
    
    'error_rate': '''
        fields @timestamp, level
        | stats count(*) as total,
                count(level = "ERROR") as errors
        by bin(5m)
        | fields total, errors, (errors / total * 100) as error_rate
    '''
}


# Example usage
if __name__ == '__main__':
    # Create logger
    logger = get_logger(tenant_id='tenant-123', service_name='user-service')
    
    # Log messages
    logger.info('User created', user_id='user-456', email='user@example.com')
    logger.warning('High memory usage', memory_mb=450)
    logger.error('Database connection failed', error='Connection timeout')
    
    # Log with structured data
    logger.log_request({
        'httpMethod': 'POST',
        'path': '/users',
        'requestContext': {
            'identity': {'sourceIp': '192.168.1.1'}
        }
    })
    
    logger.log_response(201, 123.45)
