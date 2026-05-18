import json
import os
import boto3
import sentry_sdk
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME')
table = dynamodb.Table(TABLE_NAME)

sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    traces_sample_rate=1.0
)

sentry_sdk.set_tag("module", "manageAsset")
sentry_sdk.set_tag("team", "grupo-3")


def lambda_handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        if not claims:
            # Fallback for HTTP API structure just in case
            claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        tenant_id = claims.get('custom:tenant_id') or claims.get('tenant_id')
        
        if not tenant_id:
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Unauthorized: tenant_id not found in token'})
            }

        # Check for query parameters
        query_params = event.get('queryStringParameters') or {}
        user_id = query_params.get('user_id')
        asset_type = query_params.get('type')

        items = []

        if user_id:
            # Use GSI_User
            response = table.query(
                IndexName='GSI_User',
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('user_id').eq(user_id)
            )
            items = response.get('Items', [])
        elif asset_type:
            # Use GSI_Type
            response = table.query(
                IndexName='GSI_Type',
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('type').eq(asset_type)
            )
            items = response.get('Items', [])
        else:
            # Default: Query all assets for this tenant
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('SK').begins_with("ASSET#")
            )
            items = response.get('Items', [])
        
        return {
            'statusCode': 200,
            'body': json.dumps({'assets': items})
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
