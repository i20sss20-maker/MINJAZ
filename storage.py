import hashlib
import hmac
import os
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

ALLOWED_TYPES = {
    '.pdf': {'application/pdf'},
    '.doc': {'application/msword'},
    '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    '.xls': {'application/vnd.ms-excel'},
    '.xlsx': {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
    '.ppt': {'application/vnd.ms-powerpoint'},
    '.pptx': {'application/vnd.openxmlformats-officedocument.presentationml.presentation'},
    '.jpg': {'image/jpeg'}, '.jpeg': {'image/jpeg'}, '.png': {'image/png'}, '.webp': {'image/webp'},
    '.zip': {'application/zip', 'application/x-zip-compressed'},
    '.mp4': {'video/mp4'}, '.mov': {'video/quicktime'},
    '.mp3': {'audio/mpeg'}, '.wav': {'audio/wav', 'audio/x-wav'}, '.m4a': {'audio/mp4', 'audio/x-m4a'},
}
DEFAULT_MIME = {ext: sorted(types)[0] for ext, types in ALLOWED_TYPES.items()}
DEFAULT_MAX_BYTES = 50_000_000


def _q(value):
    return urllib.parse.quote(str(value), safe='-_.~')


def _sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


class StorageError(ValueError):
    pass


class RailwayBucketStorage:
    def __init__(self, bucket=None, access_key=None, secret_key=None, region=None, endpoint=None, url_style=None, max_bytes=None):
        self.bucket=(bucket if bucket is not None else os.getenv('BUCKET','')).strip()
        self.access_key=(access_key if access_key is not None else os.getenv('ACCESS_KEY_ID','')).strip()
        self.secret_key=(secret_key if secret_key is not None else os.getenv('SECRET_ACCESS_KEY','')).strip()
        self.region=(region if region is not None else os.getenv('REGION','auto')).strip() or 'auto'
        self.endpoint=(endpoint if endpoint is not None else os.getenv('ENDPOINT','')).strip().rstrip('/')
        self.url_style=(url_style if url_style is not None else os.getenv('BUCKET_URL_STYLE','virtual')).strip().lower()
        self.max_bytes=int(max_bytes if max_bytes is not None else os.getenv('MAX_UPLOAD_BYTES',str(DEFAULT_MAX_BYTES)))
        if self.url_style not in ('virtual','path'):
            raise StorageError('invalid_bucket_url_style')

    @property
    def ready(self):
        return all((self.bucket,self.access_key,self.secret_key,self.region,self.endpoint))

    def validate_meta(self, file_name, mime_type, size_bytes):
        name=str(file_name or '').strip()
        if not name or len(name)>180:
            raise StorageError('invalid_file_name')
        name=name.replace('\\','/').split('/')[-1]
        ext=PurePosixPath(name.lower()).suffix
        if ext not in ALLOWED_TYPES:
            raise StorageError('file_type_not_allowed')
        try:
            size=int(size_bytes)
        except Exception:
            raise StorageError('invalid_file_size')
        if size<=0 or size>self.max_bytes:
            raise StorageError('file_too_large' if size>self.max_bytes else 'invalid_file_size')
        mime=str(mime_type or '').split(';',1)[0].strip().lower()
        if not mime or mime=='application/octet-stream':
            mime=DEFAULT_MIME[ext]
        if mime not in ALLOWED_TYPES[ext]:
            raise StorageError('mime_type_not_allowed')
        return {'file_name':name,'extension':ext,'mime_type':mime,'size_bytes':size}

    def object_key(self, user_id, extension, now=None):
        now=now or datetime.now(timezone.utc)
        ext=extension if extension.startswith('.') else '.'+extension
        return f"uploads/{int(user_id)}/{now.strftime('%Y/%m')}/{uuid.uuid4().hex}{ext.lower()}"

    def _target(self, key):
        if not self.ready:
            raise StorageError('storage_not_configured')
        ep=urllib.parse.urlparse(self.endpoint)
        if ep.scheme not in ('http','https') or not ep.netloc:
            raise StorageError('invalid_storage_endpoint')
        key=key.lstrip('/')
        encoded='/'.join(_q(x) for x in key.split('/'))
        if self.url_style=='virtual':
            host=f'{self.bucket}.{ep.netloc}'
            uri='/' + encoded
        else:
            host=ep.netloc
            uri='/' + _q(self.bucket) + '/' + encoded
        return ep.scheme,host,uri

    def presign(self, method, key, expires=900, content_type=None, now=None):
        method=method.upper()
        if method not in ('GET','PUT','HEAD','DELETE'):
            raise StorageError('invalid_storage_method')
        expires=max(1,min(int(expires),604800))
        now=now or datetime.now(timezone.utc)
        scheme,host,uri=self._target(key)
        datestamp=now.strftime('%Y%m%d')
        amzdate=now.strftime('%Y%m%dT%H%M%SZ')
        scope=f'{datestamp}/{self.region}/s3/aws4_request'
        headers={'host':host}
        if content_type:
            headers['content-type']=str(content_type).strip().lower()
        signed_headers=';'.join(sorted(headers))
        canonical_headers=''.join(f'{k}:{headers[k]}\n' for k in sorted(headers))
        params={
            'X-Amz-Algorithm':'AWS4-HMAC-SHA256',
            'X-Amz-Credential':f'{self.access_key}/{scope}',
            'X-Amz-Date':amzdate,
            'X-Amz-Expires':str(expires),
            'X-Amz-SignedHeaders':signed_headers,
        }
        canonical_query='&'.join(f'{_q(k)}={_q(params[k])}' for k in sorted(params))
        canonical_request='\n'.join([method,uri,canonical_query,canonical_headers,signed_headers,'UNSIGNED-PAYLOAD'])
        string_to_sign='\n'.join(['AWS4-HMAC-SHA256',amzdate,scope,hashlib.sha256(canonical_request.encode()).hexdigest()])
        k_date=_sign(('AWS4'+self.secret_key).encode(),datestamp)
        k_region=_sign(k_date,self.region)
        k_service=_sign(k_region,'s3')
        k_signing=_sign(k_service,'aws4_request')
        signature=hmac.new(k_signing,string_to_sign.encode(),hashlib.sha256).hexdigest()
        return f'{scheme}://{host}{uri}?{canonical_query}&X-Amz-Signature={signature}'

    def head(self,key,timeout=10):
        url=self.presign('HEAD',key,expires=60)
        req=urllib.request.Request(url,method='HEAD')
        with urllib.request.urlopen(req,timeout=timeout) as r:
            return {
                'size_bytes':int(r.headers.get('Content-Length') or 0),
                'mime_type':str(r.headers.get('Content-Type') or 'application/octet-stream').split(';',1)[0].lower(),
                'etag':str(r.headers.get('ETag') or '').strip('"'),
            }

    def delete(self,key,timeout=10):
        try:
            url=self.presign('DELETE',key,expires=60)
            with urllib.request.urlopen(urllib.request.Request(url,method='DELETE'),timeout=timeout):
                return True
        except Exception:
            return False

    def safe_key_for_user(self,key,user_id):
        key=str(key or '').strip().lstrip('/')
        if not re.fullmatch(r'uploads/[0-9]+/[0-9]{4}/[0-9]{2}/[a-f0-9]{32}\.[a-z0-9]+',key):
            return False
        return key.startswith(f'uploads/{int(user_id)}/')
