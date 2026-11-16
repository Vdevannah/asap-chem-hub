"""
AWS Lambda entry point (handler: api.lambda_handler.handler).

CloudFront sends /api/* to the Lambda Function URL; Mangum turns the Function URL event into an
ASGI request and strips the /api prefix, so the FastAPI routes stay /articles, /topics ...
exactly as when running locally with uvicorn.
"""

from mangum import Mangum

from .main import app

handler = Mangum(app, lifespan="off", api_gateway_base_path="/api")
