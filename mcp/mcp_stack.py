import datetime

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_logs as _logs,
    aws_s3 as _s3,
    aws_ssm as _ssm,
)
from constructs import Construct

class McpStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account = Stack.of(self).account

        year = datetime.datetime.now().strftime("%Y")
        month = datetime.datetime.now().strftime("%m")
        day = datetime.datetime.now().strftime("%d")

        bucket = _s3.Bucket.from_bucket_name(
            self,
            "PackageBucket",
            bucket_name="packages-use2-lukach-io",
        )

        fastmcp_layer = _lambda.LayerVersion(
            self,
            "FastMcpLayer",
            layer_version_name="fastmcp",
            description=f"{year}-{month}-{day} deployment",
            code=_lambda.Code.from_bucket(
                bucket=bucket,
                key="fastmcp.zip",
            ),
            compatible_architectures=[
                _lambda.Architecture.ARM_64,
            ],
            compatible_runtimes=[
                _lambda.Runtime.PYTHON_3_13,
            ],
            removal_policy=RemovalPolicy.DESTROY,
        )

        mangum_layer = _lambda.LayerVersion(
            self,
            "MangumLayer",
            layer_version_name="mangum",
            description=f"{year}-{month}-{day} deployment",
            code=_lambda.Code.from_bucket(
                bucket=bucket,
                key="mangum.zip",
            ),
            compatible_architectures=[
                _lambda.Architecture.ARM_64,
            ],
            compatible_runtimes=[
                _lambda.Runtime.PYTHON_3_13,
            ],
            removal_policy=RemovalPolicy.DESTROY,
        )

        role = _iam.Role(
            self,
            "ServiceRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        service_lambda = _lambda.Function(
            self,
            "ServiceLambda",
            function_name="mcp-service",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=_lambda.Architecture.ARM_64,
            handler="service.handler",
            code=_lambda.Code.from_asset("service"),
            description="MCP service Lambda function",
            timeout=Duration.seconds(30),
            memory_size=256,
            role=role,
            environment={
                "MCP_REGION": Stack.of(self).region,
            },
            layers=[
                fastmcp_layer,
                mangum_layer,
            ],
        )

        _logs.LogGroup(
            self,
            "ServiceLambdaLogs",
            log_group_name=f"/aws/lambda/{service_lambda.function_name}",
            retention=_logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        apigateway_account = _ssm.StringParameter.from_string_parameter_attributes(
            self,
            "ApiGatewayAccount",
            parameter_name="/account/api",
        )

        # Explicit cross-account API Gateway permission for HTTP API execute-api ARNs.
        service_lambda.add_permission(
            "AllowApiGatewayServiceInvoke",
            principal=_iam.ServicePrincipal("apigateway.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=apigateway_account.string_value,
            source_arn=(
                f"arn:aws:execute-api:{Stack.of(self).region}:"
                f"{apigateway_account.string_value}:*/*/*/mcp*"
            ),
        )

        # Keep a broader account-principal permission for non-proxy integration patterns.
        service_lambda.add_permission(
            "AllowApiAccountInvoke",
            principal=_iam.AccountPrincipal(apigateway_account.string_value),
            action="lambda:InvokeFunction",
        )

        # Set reserved concurrent executions for cost control and burst protection.
        service_lambda.reserved_concurrent_executions = 10

    ### OIDC ###

        provider = _iam.OpenIdConnectProvider(
            self, 'provider',
            url = 'https://token.actions.githubusercontent.com',
            client_ids = [
                'sts.amazonaws.com'
            ]
        )

        github = _iam.Role(
            self, 'github',
            assumed_by = _iam.WebIdentityPrincipal(provider.open_id_connect_provider_arn).with_conditions(
                {
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": "repo:jblukach/mcp:*"
                    }
                }
            )
        )

        github.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                'ReadOnlyAccess'
            )
        )   

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'cloudformation:CreateChangeSet',
                    'cloudformation:DeleteChangeSet',
                    'cloudformation:DescribeChangeSet',
                    'cloudformation:DescribeStacks',
                    'cloudformation:ExecuteChangeSet',
                    'cloudformation:CreateStack',
                    'cloudformation:UpdateStack',
                    'cloudformation:RollbackStack',
                    'cloudformation:ContinueUpdateRollback',
                    'cloudformation:DescribeStackEvents',
                    'cloudformation:GetTemplate',
                    'cloudformation:DeleteStack',
                    'cloudformation:UpdateTerminationProtection',
                    'cloudformation:GetTemplateSummary'
                ],
                resources = [
                    '*'
                ]
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    's3:GetObject*',
                    's3:GetBucket*',
                    's3:List*',
                    's3:Abort*',
                    's3:DeleteObject*',
                    's3:PutObject*'
                ],
                resources = [
                    '*'
                ]
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'kms:Decrypt',
                    'kms:DescribeKey',
                    'kms:Encrypt',
                    'kms:ReEncrypt*',
                    'kms:GenerateDataKey*'
                ],
                resources = [
                    '*'
                ],
                conditions = {
                    "StringEquals": {
                        "kms:ViaService": "s3.us-east-1.amazonaws.com"
                    }
                }
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'kms:Decrypt',
                    'kms:DescribeKey',
                    'kms:Encrypt',
                    'kms:ReEncrypt*',
                    'kms:GenerateDataKey*'
                ],
                resources = [
                    '*'
                ],
                conditions = {
                    "StringEquals": {
                        "kms:ViaService": "s3.us-east-2.amazonaws.com"
                    }
                }
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'kms:Decrypt',
                    'kms:DescribeKey',
                    'kms:Encrypt',
                    'kms:ReEncrypt*',
                    'kms:GenerateDataKey*'
                ],
                resources = [
                    '*'
                ],
                conditions = {
                    "StringEquals": {
                        "kms:ViaService": "s3.us-west-2.amazonaws.com"
                    }
                }
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'iam:PassRole'
                ],
                resources = [
                    'arn:aws:iam::'+str(account)+':role/cdk-lukach-cfn-exec-role-'+str(account)+'-us-east-1',
                    'arn:aws:iam::'+str(account)+':role/cdk-lukach-cfn-exec-role-'+str(account)+'-us-east-2',
                    'arn:aws:iam::'+str(account)+':role/cdk-lukach-cfn-exec-role-'+str(account)+'-us-west-2'
                ]
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'sts:GetCallerIdentity'
                ],
                resources = [
                    '*'
                ]
            )
        )

        github.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'ssm:GetParameter',
                    'ssm:GetParameters'
                ],
                resources = [
                    'arn:aws:ssm:us-east-1:'+str(account)+':parameter/cdk-bootstrap/lukach/version',
                    'arn:aws:ssm:us-east-2:'+str(account)+':parameter/cdk-bootstrap/lukach/version',
                    'arn:aws:ssm:us-west-2:'+str(account)+':parameter/cdk-bootstrap/lukach/version'
                ]
            )
        )
