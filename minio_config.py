from minio import Minio

minio_client = Minio('localhost:9000', access_key='s3manager', secret_key='s3manager', secure=False)
minio_bucket_name = 'bionic'
