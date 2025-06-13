import boto3
import os
from datetime import datetime, timedelta

class AWSService:
    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.ec2 = boto3.client("ec2", region_name=self.region)
        self.cloudwatch = boto3.client("cloudwatch", region_name=self.region)
        self.rds = boto3.client("rds", region_name=self.region)

    def get_cpu_utilization(self, instance_id, namespace, metric_name, dimension_name):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=3)
        metrics = self.cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{"Name": dimension_name, "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=["Average"]
        )
        datapoints = metrics.get("Datapoints", [])
        if not datapoints:
            return 0.0
        avg = sum(d["Average"] for d in datapoints) / len(datapoints)
        return round(avg, 2)

    def get_memory_utilization(self, instance_id):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=3)
        
        try:
            metrics = self.cloudwatch.get_metric_statistics(
                Namespace='CWAgent',
                MetricName='mem_used_percent',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': instance_id
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=['Average']
            )

            datapoints = metrics.get('Datapoints', [])
            if not datapoints:
                return 0.0
            avg = sum(d['Average'] for d in datapoints) / len(datapoints)
            return round(avg, 2)

        except Exception as e:
            print(f"Failed to fetch memory for {instance_id}: {e}")
            return 0.0


    def get_ec2_instance_stats(self, tenant_name=None):
        tenant_name = tenant_name or "default"
        
        try:
            response = self.ec2.describe_instances(Filters=[
                    {
                        'Name': 'tag:TENANT_NAME',
                        'Values': [tenant_name]
                    }
                ])
            if not response.get("Reservations"):
                print(f"No instances found for tenant: {tenant_name}")
                return []
        except Exception as e:
            print(f"Failed to fetch instances for tenant {tenant_name}: {e}")
            return []
        stats = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                cpu = self.get_cpu_utilization(instance_id, "AWS/EC2", "CPUUtilization", "InstanceId")
                mem = self.get_memory_utilization(instance_id)
                stats.append({
                    "id": instance_id,
                    "type": instance["InstanceType"],
                    "cpu": cpu,
                    "memory": mem,
                    "state": instance["State"]["Name"]
                })
        return stats

    def get_rds_instance_stats(self, tenant_name=None):
        tenant_name = tenant_name or "default"
        tenant_name = f"duploservices-{tenant_name}"
        tenant_filter = {"Name": "tag:Name", "Values": [tenant_name]}
        response = self.rds.describe_db_instances(Filters=[
                    tenant_filter
                ])
        stats = []
        for db in response["DBInstances"]:
            db_id = db["DBInstanceIdentifier"]
            cpu = self.get_cpu_utilization(db_id, "AWS/RDS", "CPUUtilization", "DBInstanceIdentifier")
            mem = 15.0  # Placeholder
            stats.append({
                "id": db_id,
                "class": db["DBInstanceClass"],
                "cpu": cpu,
                "memory": mem,
                "state": db["DBInstanceStatus"]
            })
        return stats
