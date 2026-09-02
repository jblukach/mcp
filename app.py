#!/usr/bin/env python3
import os

import aws_cdk as cdk

from mcp.mcp_stack import McpStack


app = cdk.App()
for stack_name, region in (
    ("McpStackUSE1", "us-east-1"),
    ("McpStack", "us-east-2"),
    ("McpStackUSW2", "us-west-2"),
):
    McpStack(
        app,
        stack_name,
        env=cdk.Environment(
            account=os.getenv("CDK_DEFAULT_ACCOUNT"),
            region=region,
        ),
        synthesizer=cdk.DefaultStackSynthesizer(
            qualifier="lukach",
        ),
    )

cdk.Tags.of(app).add("Alias", "mcp")
cdk.Tags.of(app).add("GitHub", "https://github.com/jblukach/mcp")
cdk.Tags.of(app).add("Org", "lukach.io")

app.synth()