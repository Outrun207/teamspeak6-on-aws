#!/usr/bin/env python3
import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks, NIST80053R5Checks
from stacks.teamspeak_stack import TeamspeakStack

app = cdk.App()
stack = TeamspeakStack(app, "TeamspeakStack")

# Add cdk-nag checks
cdk.Aspects.of(app).add(NIST80053R5Checks(verbose=True))

app.synth()
