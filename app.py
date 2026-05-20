import json
import os
import boto3
import sentry_sdk
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME')
table = dynamodb.Table(TABLE_NAME)

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    traces_sample_rate=1.0
)

sentry_sdk.set_tag("module", "getAssets")
sentry_sdk.set_tag("team", "grupo-3")

def make_response(success, code, data):
    return {
        'statusCode': code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': success,
            'code': code,
            'data': data
        }, default=str)
    }

def lambda_handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        if not claims:
            claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
        tenant_id = claims.get('custom:tenant_id') or claims.get('tenant_id')
        
        if not tenant_id:
            return make_response(False, 403, {'error': 'Unauthorized: tenant_id not found in token'})

        query_params = event.get('queryStringParameters') or {}
        id_producto = query_params.get('id_producto')
        tipo = query_params.get('tipo') or query_params.get('type')

        if id_producto:
            # Query specific product
            response = table.get_item(
                Key={
                    'PK': f"TENANT#{tenant_id}",
                    'SK': f"PRODUCT#{id_producto}"
                }
            )
            item = response.get('Item')
            if not item:
                return make_response(False, 404, {'error': 'Producto no encontrado'})
            
            # Format single product
            producto = {
                'id_producto': item.get('id_producto'),
                'nombre': item.get('nombre'),
                'descripcion': item.get('descripcion'),
                'tipo': item.get('tipo') or item.get('type'),
                'fecha_de_registro': item.get('fecha_de_registro'),
                'stock': int(item.get('stock', 0))
            }
            return make_response(True, 200, {'producto': producto})
            
        elif tipo:
            # Use GSI_Type (PK and type). GSI is defined with range key 'type' on AWS
            response = table.query(
                IndexName='GSI_Type',
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('type').eq(tipo)
            )
            items = response.get('Items', [])
        else:
            # Default: Query all products for this tenant
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('SK').begins_with("PRODUCT#")
            )
            items = response.get('Items', [])
            
        # Format list of products
        productos = []
        for item in items:
            productos.append({
                'id_producto': item.get('id_producto'),
                'nombre': item.get('nombre'),
                'descripcion': item.get('descripcion'),
                'tipo': item.get('tipo') or item.get('type'),
                'fecha_de_registro': item.get('fecha_de_registro'),
                'stock': int(item.get('stock', 0))
            })
            
        return make_response(True, 200, {'productos': productos})

    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Error: {str(e)}")
        return make_response(False, 500, {'error': 'Internal server error'})
