import json
import os
import boto3
import sentry_sdk
from boto3.dynamodb.conditions import Key

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME')
table = dynamodb.Table(TABLE_NAME)

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

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
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'success': success,
            'code': code,
            'data': data
        }, default=str)
    }


def get_secure_image_url(stored_url):
    """
    Generates a secure presigned GET URL for product images stored in S3.
    """
    if not stored_url:
        return ""
    
    # Extract S3 key if it starts with s3://
    key = stored_url
    if stored_url.startswith("s3://"):
        parts = stored_url[5:].split('/', 1)
        if len(parts) == 2:
            key = parts[1]
            
    # Check if it represents a product image in our S3 bucket
    if key.startswith("products/") or "/" in key:
        if not BUCKET_NAME:
            print("Warning: BUCKET_NAME not configured. Returning original stored URL.")
            return stored_url
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': key
                },
                ExpiresIn=3600  # Valid for 1 hour
            )
            return presigned_url
        except Exception as e:
            print(f"Error generating presigned GET URL for {key}: {str(e)}")
            return stored_url  # Fallback to stored S3 URI
            
    return stored_url  # Return original if it is a standard URL or other string


def format_producto(item):
    """
    Formats product attributes. Excludes discount_price if it is 0.
    """
    producto = {
        'id_producto': item.get('product_id') or item.get('id_producto'),
        'product_id': item.get('product_id') or item.get('id_producto'),
        'name': item.get('name') or item.get('nombre'),
        'description': item.get('description') or item.get('descripcion', ''),
        'category': item.get('category') or item.get('tipo') or item.get('type', ''),
        'price': float(item.get('price', 0.0)),
        'stock': int(item.get('stock', 0)),
        'image_url': get_secure_image_url(item.get('image_url')),
        'status': item.get('status', 'ACTIVE'),
        'created_at': item.get('created_at'),
        'updated_at': item.get('updated_at')
    }

    # Exclude discount_price when it is 0
    discount_price = float(item.get('discount_price', 0.0))
    if discount_price != 0.0:
        producto['discount_price'] = discount_price

    return producto


def lambda_handler(event, context):
    try:
        # Secure Claims Parsing (prevents crashes when claims are missing or empty)
        claims = {}
        request_context = event.get('requestContext')
        if request_context and isinstance(request_context, dict):
            authorizer = request_context.get('authorizer')
            if authorizer and isinstance(authorizer, dict):
                claims = authorizer.get('claims') or authorizer.get('jwt', {}).get('claims', {}) or {}

        # Fixed single tenant ID
        tenant_id = "Ecommerce00"

        # Parse query params
        query_params = event.get('queryStringParameters') or {}
        id_producto = query_params.get('product_id') or query_params.get('id_producto')
        category = query_params.get('category') or query_params.get('tipo') or query_params.get('type')
        status_filter = query_params.get('status')

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
            
            return make_response(True, 200, {'producto': format_producto(item)})
            
        elif category:
            # Query by GSI_Type
            response = table.query(
                IndexName='GSI_Type',
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('type').eq(category)
            )
            items = response.get('Items', [])
            
            # Apply basic filtering (status)
            if status_filter:
                items = [item for item in items if item.get('status') == status_filter]
                
        else:
            # Query all products for this tenant
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"TENANT#{tenant_id}") & Key('SK').begins_with("PRODUCT#")
            )
            items = response.get('Items', [])
            
            # Apply basic filtering (status)
            if status_filter:
                items = [item for item in items if item.get('status') == status_filter]

        # Format list of products
        productos = [format_producto(item) for item in items]
            
        return make_response(True, 200, {'productos': productos})

    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"Error: {str(e)}")
        return make_response(False, 500, {'error': f'Internal server error: {str(e)}'})
