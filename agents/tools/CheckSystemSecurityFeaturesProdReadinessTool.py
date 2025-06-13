from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator

class CheckSystemSecurityFeaturesProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
            {
                'name': 'vpc_flow_logs',
                'attribute_path': ['EnableVpcFlowLogs'],
                'condition': lambda val: (val is True,
                                        "VPC Flow Logs are enabled" if val is True else "VPC Flow Logs are not enabled"),
                'severity': 'critical',
                'recommendation': "Enable VPC Flow Logs to monitor network traffic for security analysis and troubleshooting"
            },
            {
                'name': 'security_hub',
                'attribute_path': ['EnableSecurityHub'],
                'condition': lambda val: (val is True,
                                        "AWS Security Hub is enabled" if val is True else "AWS Security Hub is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS Security Hub for comprehensive security compliance monitoring"
            },
            {
                'name': 'guard_duty',
                'attribute_path': ['EnableGuardDuty'],
                'condition': lambda val: (val is True,
                                        "AWS GuardDuty is enabled" if val is True else "AWS GuardDuty is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS GuardDuty for threat detection and continuous security monitoring"
            },
            {
                'name': 'cloud_trail',
                'attribute_path': ['EnableCloudTrail'],
                'condition': lambda val: (val is True,
                                        "AWS CloudTrail is enabled" if val is True else "AWS CloudTrail is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS CloudTrail for comprehensive API activity tracking and auditing"
            },
            {
                'name': 'password_policy',
                'attribute_path': ['EnablePasswordPolicy'],
                'condition': lambda val: (val is True,
                                        "AWS Password Policy is enabled" if val is True else "AWS Password Policy is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable AWS Password Policy to enforce strong password requirements"
            },
            {
                'name': 's3_public_access_block',
                'attribute_path': ['EnableGlobalS3PublicAccessBlock'],
                'condition': lambda val: (val is True,
                                        "Global S3 Public Access Block is enabled" if val is True else "Global S3 Public Access Block is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Global S3 Public Access Block to prevent accidental public exposure of S3 buckets"
            },
            {
                'name': 'inspector',
                'attribute_path': ['EnableInspector'],
                'condition': lambda val: (val is True,
                                        "AWS Inspector is enabled" if val is True else "AWS Inspector is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable AWS Inspector for automated security assessment and vulnerability identification"
            },
            {
                'name': 'cis_cloudtrail_cloudwatch_alarms',
                'attribute_path': ['EnableCisCloudTrailCloudWatchAlarms'],
                'condition': lambda val: (val is True,
                                        "CIS CloudTrail CloudWatch Alarms are enabled" if val is True else "CIS CloudTrail CloudWatch Alarms are not enabled"),
                'severity': 'warning',
                'recommendation': "Enable CIS CloudTrail CloudWatch Alarms for monitoring and alerting on suspicious activities"
            },
            {
                'name': 'all_security_hub_regions',
                'attribute_path': ['EnableAllSecurityHubRegions'],
                'condition': lambda val: (val is True,
                                        "Security Hub is enabled in all regions" if val is True else "Security Hub is not enabled in all regions"),
                'severity': 'warning',
                'recommendation': "Enable Security Hub in all regions to ensure comprehensive security coverage"
            },
            {
                'name': 'all_inspector_regions',
                'attribute_path': ['EnableAllInspectorRegions'],
                'condition': lambda val: (val is True,
                                        "Inspector is enabled in all regions" if val is True else "Inspector is not enabled in all regions"),
                'severity': 'warning',
                'recommendation': "Enable Inspector in all regions to ensure comprehensive vulnerability assessment"
            },
            {
                'name': 'delete_default_vpcs',
                'attribute_path': ['DeleteDefaultVpcs'],
                'condition': lambda val: (val is True,
                                        "Default VPCs are deleted" if val is True else "Default VPCs are not deleted"),
                'severity': 'warning',
                'recommendation': "Delete default VPCs to reduce the attack surface and enforce explicit network configuration"
            },
            {
                'name': 'revoke_default_sg_rules',
                'attribute_path': ['RevokeDefaultSgRules'],
                'condition': lambda val: (val is True,
                                        "Default security group rules are revoked" if val is True else "Default security group rules are not revoked"),
                'severity': 'warning',
                'recommendation': "Revoke default security group rules to enforce explicit security group configuration"
            }
        ])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_system_security_features_prod_readiness",
            "description": "Checks input system security features for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                     "EnableVpcFlowLogs": {
                         "type": "boolean",
                         "description": "Whether VPC flow logs to monitor network traffic for security analysis/troubleshooting have been enabled"
                     },
                     "EnableSecurityHub": {
                         "type": "boolean",
                         "description": "Whether AWS Security Hub for comprehensive security compliance monitoring is enabled"
                     },
                     "EnableGuardDuty": {
                         "type": "boolean",
                         "description": "Whether GuardDuty for threat detection and continuous security monitoring has been enabled"
                     },
                     "EnableCloudTrail": {
                         "type": "boolean",
                         "description": "Whether Cloudtrail for comprehensive API activity tracking and auditing has been enabled"
                     },
                     "EnablePasswordPolicy": {
                         "type": "boolean",
                         "description": "Whether AWS Password Policy to enforce strong password requirements has been enabled"
                     },
                     "EnableGlobalS3PublicAccessBlock": {
                         "type": "boolean",
                         "description": "Whether global S3 Public Access Block to prevent accidental public exposure of S3 buckets has been enabled"
                     },
                     "EnableInspector": {
                         "type": "boolean",
                         "description": "Whether AWS Inspector for automated security assessment and vulnerability identification has been enabled"
                     },
                     "EnableCisCloudTrailCloudWatchAlarms": {
                         "type": "boolean",
                         "description": "Whether CIS CloudTrail CloudWatch Alarms for monitoring and alerting on suspicious activities has been enabled"
                     },
                     "EnableAllSecurityHubRegions": {
                         "type": "boolean",
                         "description": "Whether Security Hub has been enabled in all relevant regions to ensure comprehensive security coverage"
                     },
                     "EnableAllInspectorRegions": {
                         "type": "boolean",
                         "description": "Whether AWS Inspector has been enabled in all relevant regions to ensure comprehensive vulnerability assessment"
                     },
                     "DeleteDefaultVpcs": {
                         "type": "boolean",
                         "description": "Whether default VPCs have been deleted so we reduce the attack surface and enforce explicit network configuration"
                     },
                     "RevokeDefaultSgRules": {
                         "type": "boolean",
                         "description": "Whether default security group rules have been revoked to enforce explicit security group configuration"
                     }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.evaluator.evaluate(resources)
