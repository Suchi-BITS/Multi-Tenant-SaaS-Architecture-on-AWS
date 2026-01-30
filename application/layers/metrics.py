"""
Metrics Layer for Multi-Tenant SaaS
Provides CloudWatch metrics publishing with tenant context
"""

import boto3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

class MetricUnit(Enum):
    """CloudWatch metric units"""
    COUNT = 'Count'
    SECONDS = 'Seconds'
    MILLISECONDS = 'Milliseconds'
    BYTES = 'Bytes'
    KILOBYTES = 'Kilobytes'
    MEGABYTES = 'Megabytes'
    PERCENT = 'Percent'


class TenantMetrics:
    """CloudWatch metrics publisher with tenant context"""
    
    def __init__(self, tenant_id: str = None, namespace: str = None):
        self.tenant_id = tenant_id
        self.namespace = namespace or 'MultiTenantSaaS'
        self.cloudwatch = boto3.client('cloudwatch')
        self.batch = []
        self.batch_size = 20  # CloudWatch limit
    
    def put_metric(self, 
                   metric_name: str, 
                   value: float, 
                   unit: MetricUnit = MetricUnit.COUNT,
                   dimensions: Dict[str, str] = None):
        """
        Publish a metric to CloudWatch
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            dimensions: Additional dimensions (tenant_id is added automatically)
        """
        metric_dimensions = []
        
        # Add tenant dimension if available
        if self.tenant_id:
            metric_dimensions.append({
                'Name': 'TenantId',
                'Value': self.tenant_id
            })
        
        # Add custom dimensions
        if dimensions:
            for key, val in dimensions.items():
                metric_dimensions.append({
                    'Name': key,
                    'Value': str(val)
                })
        
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit.value,
            'Timestamp': datetime.utcnow(),
            'Dimensions': metric_dimensions
        }
        
        self.batch.append(metric_data)
        
        # Flush if batch is full
        if len(self.batch) >= self.batch_size:
            self.flush()
    
    def flush(self):
        """Flush batched metrics to CloudWatch"""
        if not self.batch:
            return
        
        try:
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=self.batch
            )
            self.batch = []
        except Exception as e:
            print(f"Error publishing metrics: {str(e)}")
    
    def __del__(self):
        """Ensure metrics are flushed when object is destroyed"""
        self.flush()
    
    # Convenience methods for common metrics
    
    def record_api_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Record API request metrics"""
        self.put_metric('APIRequests', 1, MetricUnit.COUNT, {
            'Method': method,
            'Path': path
        })
        
        self.put_metric('APILatency', duration_ms, MetricUnit.MILLISECONDS, {
            'Method': method,
            'Path': path
        })
        
        if status_code >= 500:
            self.put_metric('APIErrors', 1, MetricUnit.COUNT, {
                'StatusCode': str(status_code)
            })
    
    def record_database_query(self, operation: str, duration_ms: float, row_count: int = None):
        """Record database query metrics"""
        self.put_metric('DatabaseQueries', 1, MetricUnit.COUNT, {
            'Operation': operation
        })
        
        self.put_metric('DatabaseQueryDuration', duration_ms, MetricUnit.MILLISECONDS, {
            'Operation': operation
        })
        
        if row_count is not None:
            self.put_metric('DatabaseRowsAffected', row_count, MetricUnit.COUNT, {
                'Operation': operation
            })
    
    def record_cache_hit(self, cache_name: str):
        """Record cache hit"""
        self.put_metric('CacheHits', 1, MetricUnit.COUNT, {
            'CacheName': cache_name
        })
    
    def record_cache_miss(self, cache_name: str):
        """Record cache miss"""
        self.put_metric('CacheMisses', 1, MetricUnit.COUNT, {
            'CacheName': cache_name
        })
    
    def record_user_action(self, action: str):
        """Record user action"""
        self.put_metric('UserActions', 1, MetricUnit.COUNT, {
            'Action': action
        })
    
    def record_business_metric(self, metric_name: str, value: float, unit: MetricUnit = MetricUnit.COUNT):
        """Record business metric (orders, revenue, etc.)"""
        self.put_metric(metric_name, value, unit)
    
    def record_resource_usage(self, resource: str, usage: float, unit: MetricUnit = MetricUnit.PERCENT):
        """Record resource usage metric"""
        self.put_metric('ResourceUsage', usage, unit, {
            'Resource': resource
        })


def get_metrics(tenant_id: str = None, namespace: str = None) -> TenantMetrics:
    """Get tenant-aware metrics publisher"""
    return TenantMetrics(tenant_id, namespace)


class MetricCollector:
    """Context manager for collecting metrics"""
    
    def __init__(self, metrics: TenantMetrics, metric_name: str, unit: MetricUnit = MetricUnit.MILLISECONDS):
        self.metrics = metrics
        self.metric_name = metric_name
        self.unit = unit
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds() * 1000
        self.metrics.put_metric(self.metric_name, duration, self.unit)


# Decorator for timing functions
def timed_metric(metric_name: str):
    """Decorator to automatically time and record function execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try to get metrics from kwargs
            metrics = kwargs.get('metrics')
            
            start_time = datetime.utcnow()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                if metrics:
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    metrics.put_metric(metric_name, duration, MetricUnit.MILLISECONDS)
        
        return wrapper
    return decorator


# Example usage
if __name__ == '__main__':
    # Create metrics publisher
    metrics = get_metrics(tenant_id='tenant-123')
    
    # Record various metrics
    metrics.record_api_request('POST', '/users', 201, 125.5)
    metrics.record_database_query('INSERT', 45.3, row_count=1)
    metrics.record_user_action('user_created')
    metrics.record_business_metric('Orders', 1, MetricUnit.COUNT)
    
    # Use context manager for timing
    with MetricCollector(metrics, 'ProcessingTime'):
        # Do some work
        import time
        time.sleep(0.1)
    
    # Flush metrics
    metrics.flush()
    
    # Using decorator
    @timed_metric('DataProcessing')
    def process_data(data, metrics=None):
        # Process data
        pass
    
    process_data({'key': 'value'}, metrics=metrics)
