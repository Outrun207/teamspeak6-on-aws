#!/usr/bin/env python3
import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks, NIST80053R5Checks
from stacks.teamspeak_stack import TeamspeakStack
import os

app = cdk.App()

# Get account and region from environment or use defaults for synth
env = cdk.Environment(
    account=os.environ.get('CDK_DEFAULT_ACCOUNT', os.environ.get('AWS_ACCOUNT_ID')),
    region=os.environ.get('CDK_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
)

stack = TeamspeakStack(app, "TeamspeakStack", env=env)

# Add cdk-nag checks
cdk.Aspects.of(app).add(NIST80053R5Checks(verbose=True))

app.synth()
