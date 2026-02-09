# TeamSpeak 6 Server on AWS

Automated deployment of TeamSpeak 6 server using AWS CDK (Python) with auto-patching and auto-updates.

## Architecture

- **EC2**: t3.micro (x86-64, 2 vCPU, 1GB RAM) - ~$7.50/month
- **OS**: Amazon Linux 2023 (auto-patched weekly via SSM Patch Manager)
- **Container**: TeamSpeak 6 Docker image (auto-updated weekly via Watchtower)
- **Storage**: 13GB EBS volume (encrypted, persistent, survives instance replacement)
- **Network**: Elastic IP for consistent address

## Features

- ✅ Persistent storage for chats and data
- ✅ Automatic OS patching (Sundays at 2 AM UTC)
- ✅ Automatic TeamSpeak updates (weekly check)
- ✅ Auto-restart on instance reboot
- ✅ Supports 5-6 users with gameplay streaming
- ✅ Configurable VPC (default or custom)

## Prerequisites

1. AWS Account
2. AWS CLI configured
3. Python 3.11+
4. Node.js (for CDK CLI)

## Configuration

Edit `config.json` to customize deployment:

```json
{
  "vpc_id": null,
  "subnet_id": null,
  "teamspeak_image": "teamspeaksystems/teamspeak6-server:latest",
  "watchtower_image": "containrrr/watchtower",
  "instance_type": "t3.micro",
  "volume_size": 13,
  "patch_schedule": "cron(0 2 ? * SUN *)",
  "watchtower_interval": 604800
}
```

**Network:**
- `vpc_id`: Leave as `null` to use default VPC (recommended), or specify VPC ID (e.g., `"vpc-12345678"`)
- `subnet_id`: Optional subnet ID when using custom VPC (e.g., `"subnet-12345678"`)

**Container Images:**
- `teamspeak_image`: Pin a specific version (e.g., `"teamspeaksystems/teamspeak6-server:6.0.1"`) or use `latest`
- `watchtower_image`: Customize if needed (default: `"containrrr/watchtower"`)

**Instance:**
- `instance_type`: EC2 instance type (default: `"t3.micro"`, options: `"t3.small"`, `"t3.medium"`, etc.)
- `volume_size`: EBS volume size in GB (default: `13`, minimum: `8`)

**Maintenance:**
- `patch_schedule`: Cron expression for OS patching (default: Sundays at 2 AM UTC)
  - Examples: `"cron(0 3 ? * MON *)"` (Mondays 3 AM), `"cron(0 2 1 * ? *)"` (1st of month 2 AM)
- `watchtower_interval`: Container update check interval in seconds (default: `604800` = weekly)
  - Daily: `86400`, Weekly: `604800`, Monthly: `2592000`

## Local Deployment

```bash
# Install dependencies
pip install -r requirements.txt
npm install -g aws-cdk

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy
cdk deploy
```

## GitHub Actions Deployment

### Setup OIDC (Recommended - No Access Keys)

**Step 1: Create IAM OIDC Identity Provider**

1. Go to AWS Console → IAM → Identity providers → Add provider
2. Configure:
   - **Provider type**: OpenID Connect
   - **Provider URL**: `https://token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`
3. Click "Add provider"

**Step 2: Create IAM Role for GitHub Actions**

1. Go to IAM → Roles → Create role
2. Select "Web identity"
3. Choose the OIDC provider you just created
4. **Audience**: Select `sts.amazonaws.com`
5. Click "Next"

**Step 3: Configure Trust Policy**

Edit the trust policy to restrict to your specific repository:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<YOUR_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:<YOUR_GITHUB_USERNAME>/teamspeak-server:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Replace:
- `<YOUR_ACCOUNT_ID>` with your AWS account ID (12 digits)
- `<YOUR_GITHUB_USERNAME>` with your GitHub username

**Step 4: Attach Permissions**

1. Click "Next" to permissions
2. Attach `AdministratorAccess` policy (or create a more restrictive policy for production)
3. Name the role: `GitHubActionsTeamSpeakRole`
4. Click "Create role"

**Step 5: Add GitHub Secrets**

1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Click "New repository secret" and add:

   - **Name**: `AWS_ROLE_ARN`
   - **Value**: `arn:aws:iam::<YOUR_ACCOUNT_ID>:role/GitHubActionsTeamSpeakRole`

   - **Name**: `AWS_REGION`
   - **Value**: `us-east-1` (or your preferred region)

**Step 6: Deploy**

Push to `main` branch to trigger deployment.

## Connecting

After deployment, the stack outputs the server IP:
```
Connect to: <IP_ADDRESS>:9987
```

Use this address in your TeamSpeak 6 client.

## Costs

Estimated monthly cost (us-east-1):
- EC2 t3.micro: ~$7.50
- EBS 13GB gp3: ~$1.04
- Elastic IP: $0 (free while attached)
- Data transfer: ~$1-2
- **Total: ~$9.50-10.50/month**

## Maintenance

- **OS patches**: Automatic (Sundays 2 AM UTC)
- **TeamSpeak updates**: Automatic (weekly check)
- **Backups**: Configure AWS Backup for EBS snapshots (optional)

## Monitoring

Access instance via SSM Session Manager:
```bash
aws ssm start-session --target <instance-id>
```

Check logs:
```bash
cd /opt/teamspeak
docker-compose logs -f
```

## Cleanup

```bash
cdk destroy
```

Note: EBS volume has `delete_on_termination=False` to preserve data. Delete manually if needed.
