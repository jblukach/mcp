#!/usr/bin/env python3
import os

import aws_cdk as cdk

from mcp.mcp_stack import McpStack


app = cdk.App()
McpStack(
    app,
    "McpStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region="us-east-2",
    ),
    synthesizer=cdk.DefaultStackSynthesizer(
        qualifier="lukach",
    ),
)

cdk.Tags.of(app).add("Alias", "mcp")
cdk.Tags.of(app).add("GitHub", "https://github.com/jblukach/mcp")
cdk.Tags.of(app).add("Org", "lukach.io")

app.synth()