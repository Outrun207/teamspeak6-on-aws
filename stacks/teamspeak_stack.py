from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    CfnOutput,
    Aspects,
)
from constructs import Construct
from cdk_nag import NagSuppressions, NagPackSuppression
import json
import os

class TeamspeakStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load config
        with open("config.json") as f:
            config = json.load(f)

        # Get alert email from env var (for GitHub secrets) or config
        alert_email = os.environ.get("ALERT_EMAIL") or config.get("alert_email")

        # VPC - use default or specified
        if config.get("vpc_id"):
            vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=config["vpc_id"])
            subnet_selection = ec2.SubnetSelection(subnet_ids=[config["subnet_id"]]) if config.get("subnet_id") else ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        else:
            vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)
            subnet_selection = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)

        # Security Group
        sg = ec2.SecurityGroup(self, "TeamspeakSG",
            vpc=vpc,
            description="TeamSpeak 6 Server",
            allow_all_outbound=True
        )
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.udp(9987), "TS6 Voice")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(30033), "TS6 File Transfer")

        # IAM Role for SSM and Patch Manager
        role = iam.Role(self, "TeamspeakRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        # User data script
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "yum update -y",
            "yum install -y docker",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -aG docker ec2-user",
            
            # Install Docker Compose
            "curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose",
            "chmod +x /usr/local/bin/docker-compose",
            
            # Create TeamSpeak directory
            "mkdir -p /opt/teamspeak/data",
            
            # Create docker-compose.yml
            "cat > /opt/teamspeak/docker-compose.yml << 'EOF'",
            "services:",
            "  teamspeak:",
            f"    image: {config.get('teamspeak_image', 'teamspeaksystems/teamspeak6-server:latest')}",
            "    container_name: teamspeak6",
            "    restart: unless-stopped",
            "    ports:",
            "      - \"9987:9987/udp\"",
            "      - \"30033:30033/tcp\"",
            "    volumes:",
            "      - /opt/teamspeak/data:/var/tsserver",
            "    environment:",
            "      - TSSERVER_LICENSE_ACCEPTED=accept",
            "    labels:",
            "      - com.centurylinklabs.watchtower.enable=true",
            "",
            "  watchtower:",
            f"    image: {config.get('watchtower_image', 'containrrr/watchtower')}",
            "    container_name: watchtower",
            "    restart: unless-stopped",
            "    volumes:",
            "      - /var/run/docker.sock:/var/run/docker.sock",
            f"    command: --interval {config.get('watchtower_interval', 604800)} --cleanup",
            "EOF",
            
            # Start services
            "cd /opt/teamspeak",
            "docker-compose up -d",
            
            # Create systemd service for auto-start
            "cat > /etc/systemd/system/teamspeak.service << 'EOF'",
            "[Unit]",
            "Description=TeamSpeak 6 Server",
            "Requires=docker.service",
            "After=docker.service",
            "",
            "[Service]",
            "Type=oneshot",
            "RemainAfterExit=yes",
            "WorkingDirectory=/opt/teamspeak",
            "ExecStart=/usr/local/bin/docker-compose up -d",
            "ExecStop=/usr/local/bin/docker-compose down",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            
            "systemctl enable teamspeak.service"
        )

        # EC2 Instance
        instance = ec2.Instance(self, "TeamspeakInstance",
            instance_type=ec2.InstanceType(config.get("instance_type", "t3.micro")),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.X86_64
            ),
            vpc=vpc,
            vpc_subnets=subnet_selection,
            security_group=sg,
            role=role,
            user_data=user_data,
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=config.get("volume_size", 13),
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=False,
                        encrypted=True
                    )
                )
            ]
        )

        # Elastic IP
        eip = ec2.CfnEIP(self, "TeamspeakEIP",
            instance_id=instance.instance_id
        )

        # SSM Patch Baseline Association
        ssm.CfnAssociation(self, "PatchAssociation",
            name="AWS-RunPatchBaseline",
            targets=[{
                "key": "InstanceIds",
                "values": [instance.instance_id]
            }],
            schedule_expression=config.get("patch_schedule", "cron(0 2 ? * SUN *)"),
            parameters={
                "Operation": ["Install"],
                "RebootOption": ["RebootIfNeeded"]
            },
            association_name="TeamSpeakPatchBaseline"
        )

        # Outputs
        CfnOutput(self, "ServerIP", 
            value=eip.attr_public_ip,
            description="Public IP address of TeamSpeak server"
        )
        CfnOutput(self, "ConnectCommand", 
            value=f"Connect to: {eip.attr_public_ip}:9987",
            description="Use this address in your TeamSpeak 6 client"
        )
        CfnOutput(self, "InstanceId", 
            value=instance.instance_id,
            description="EC2 instance ID for SSM access"
        )
        CfnOutput(self, "SSMSessionCommand",
            value=f"aws ssm start-session --target {instance.instance_id}",
            description="Command to connect via SSM Session Manager"
        )
        CfnOutput(self, "GetAdminTokenCommand",
            value=f"aws ssm start-session --target {instance.instance_id} --document-name AWS-StartNonInteractiveCommand --parameters command='sudo docker logs teamspeak6 | grep -i token'",
            description="Command to retrieve TeamSpeak admin token (only shown on first startup)"
        )
        CfnOutput(self, "SecurityGroupId",
            value=sg.security_group_id,
            description="Security group ID"
        )

        # Monitoring - SNS topic and CloudWatch alarm
        if alert_email:
            topic = sns.Topic(self, "AlertTopic",
                display_name="TeamSpeak Server Alerts"
            )
            topic.add_subscription(
                sns_subs.EmailSubscription(alert_email)
            )

            alarm = cw.Alarm(self, "InstanceDownAlarm",
                metric=cw.Metric(
                    namespace="AWS/EC2",
                    metric_name="StatusCheckFailed",
                    dimensions_map={"InstanceId": instance.instance_id},
                    period=cw.Duration.minutes(5),
                    statistic="Maximum"
                ),
                threshold=1,
                evaluation_periods=2,
                datapoints_to_alarm=2,
                alarm_description="TeamSpeak server is down or unreachable",
                treat_missing_data=cw.TreatMissingData.BREACHING
            )
            alarm.add_alarm_action(cw_actions.SnsAction(topic))

            CfnOutput(self, "AlertEmail", value=alert_email)

        # Suppress cdk-nag findings that are acceptable for this use case
        NagSuppressions.add_stack_suppressions(self, [
            NagPackSuppression(
                id="NIST.800.53.R5-EC2RestrictedSSH",
                reason="TeamSpeak requires public UDP/TCP access on specific ports"
            ),
            NagPackSuppression(
                id="NIST.800.53.R5-EC2RestrictedCommon",
                reason="TeamSpeak requires public UDP/TCP access on specific ports"
            ),
            NagPackSuppression(
                id="NIST.800.53.R5-IAMNoInlinePolicy",
                reason="Using AWS managed policies for SSM and CloudWatch"
            ),
            NagPackSuppression(
                id="NIST.800.53.R5-EBSInBackupPlan",
                reason="Backup plan is optional for this deployment, can be added separately"
            ),
            NagPackSuppression(
                id="NIST.800.53.R5-EC2EBSOptimizedInstance",
                reason="t4g.micro does not support EBS optimization"
            ),
            NagPackSuppression(
                id="NIST.800.53.R5-SNSEncryptedKMS",
                reason="Email notifications do not require KMS encryption for this use case"
            )
        ])
