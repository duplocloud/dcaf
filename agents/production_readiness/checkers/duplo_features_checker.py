# duplo_features_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class DuploFeaturesProductionReadinessChecker(BaseChecker):
    """Checker for DuploCloud features production readiness"""
    
    def check(self, tenant: str) -> Dict[str, Any]:
        """
        Check DuploCloud features for production readiness
        
        Args:
            tenant: Tenant name or ID
            
        Returns:
            Dictionary with check results
        """
        # Fetch DuploCloud features
        logging_config = self.get_resources(tenant, "duplo_logging")
        monitoring_config = self.get_resources(tenant, "duplo_monitoring")
        alerting_config = self.get_resources(tenant, "duplo_alerting")
        notification_config = self.get_resources(tenant, "duplo_notification")
        
        # Check logging
        logging_enabled = self._check_logging_enabled(tenant, logging_config)
        
        # Check monitoring
        monitoring_enabled = self._check_monitoring_enabled(tenant, monitoring_config)
        
        # Check alerting
        alerting_enabled = self._check_alerting_enabled(tenant, alerting_config)
        
        # Check notifications
        notification_configured = self._check_notification_configured(tenant, notification_config)
        
        # Combine results
        results = {
            "logging": logging_enabled,
            "monitoring": monitoring_enabled,
            "alerting": alerting_enabled,
            "notification": notification_configured
        }
        
        # Calculate overall score
        total_checks = 4
        passed_checks = sum(1 for result in results.values() if result.get("passed", False))
        score = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
        
        return {
            "resource_type": "duplo_features",
            "tenant": tenant,
            "results": results,
            "score": score,
            "passed": score >= 75,  # Pass if at least 75% of checks pass
            "message": f"DuploCloud features check: {passed_checks}/{total_checks} checks passed"
        }
    
    def _check_logging_enabled(self, tenant: str, logging_config: Any) -> Dict[str, Any]:
        """Check if logging is enabled for the tenant"""
        enabled = False
        message = "Logging is not enabled"
        
        if isinstance(logging_config, list):
            # Check if tenant is in the list of tenants with logging enabled
            enabled = any(config.get("TenantId") == tenant for config in logging_config)
            message = "Logging is enabled" if enabled else "Logging is not enabled"
        
        return {
            "name": "logging_enabled",
            "passed": enabled,
            "severity": "critical",
            "message": message,
            "recommendation": "Enable logging for better observability and troubleshooting" if not enabled else ""
        }
    
    def _check_monitoring_enabled(self, tenant: str, monitoring_config: Any) -> Dict[str, Any]:
        """Check if monitoring is enabled for the tenant"""
        enabled = False
        message = "Monitoring is not enabled"
        
        if isinstance(monitoring_config, dict):
            # Check if monitoring is enabled in the config
            enabled = monitoring_config.get("Enabled", False)
            message = "Monitoring is enabled" if enabled else "Monitoring is not enabled"
        
        return {
            "name": "monitoring_enabled",
            "passed": enabled,
            "severity": "critical",
            "message": message,
            "recommendation": "Enable monitoring for better observability and alerting" if not enabled else ""
        }
    
    def _check_alerting_enabled(self, tenant: str, alerting_config: Any) -> Dict[str, Any]:
        """Check if alerting is enabled for the tenant"""
        enabled = False
        message = "Alerting is not enabled"
        
        if isinstance(alerting_config, dict):
            # Check if alerting is enabled in the config
            enabled = alerting_config.get("Value") == "true"
            message = "Alerting is enabled" if enabled else "Alerting is not enabled"
        
        return {
            "name": "alerting_enabled",
            "passed": enabled,
            "severity": "critical",
            "message": message,
            "recommendation": "Enable alerting for automatic notifications on issues" if not enabled else ""
        }
    
    def _check_notification_configured(self, tenant: str, notification_config: Any) -> Dict[str, Any]:
        """Check if notifications are configured for the tenant"""
        email_configured = False
        sns_configured = False
        message = "Notifications are not configured"
        
        if isinstance(notification_config, dict):
            # Check if email or SNS notifications are configured
            email_configured = bool(notification_config.get("NotificationEmail"))
            sns_configured = bool(notification_config.get("NotificationSNS"))
            
            if email_configured and sns_configured:
                message = "Email and SNS notifications are configured"
            elif email_configured:
                message = "Email notifications are configured"
            elif sns_configured:
                message = "SNS notifications are configured"
        
        return {
            "name": "notification_configured",
            "passed": email_configured or sns_configured,
            "severity": "warning",
            "message": message,
            "recommendation": "Configure notification channels for alerts" if not (email_configured or sns_configured) else ""
        }