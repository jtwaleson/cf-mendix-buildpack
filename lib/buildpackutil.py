import os
import re
import json


def get_database_config():
    url = os.environ['DATABASE_URL']
    pattern = r'([a-zA-Z]+)://([^:]+):([^@]+)@([^/]+)/(.*)'
    match = re.search(pattern, url)
    supported_databases = {
        'postgres':  'PostgreSQL',
        'mysql': 'MySQL',
    }

    if match is None:
        raise Exception(
            'Could not parse DATABASE_URL environment variable %s' % url
        )

    database_type_input = match.group(1)
    if match.group(1) not in supported_databases:
        raise Exception('Unknown database type: %s', database_type_input)
    database_type = supported_databases[database_type_input]

    return {
        'DatabaseType': database_type,
        'DatabaseUserName': match.group(2),
        'DatabasePassword': match.group(3),
        'DatabaseHost': match.group(4),
        'DatabaseName': match.group(5),
    }


def get_vcap_services_data():
    if os.environ.get('VCAP_SERVICES'):
        return json.loads(os.environ.get('VCAP_SERVICES'))
    else:
        return None


def get_new_relic_license_key():
    vcap_services = get_vcap_services_data()
    if vcap_services and 'newrelic' in vcap_services:
        return vcap_services['newrelic'][0]['credentials']['licenseKey']
    return None


def get_s3fs_args(mountpoint):
    key_id = os.environ.get('AWSACCESSKEYID')
    key_secret = os.environ.get('AWSSECRETACCESSKEY')
    bucket_name = os.environ.get('BUCKET_NAME')
    cwd = os.getcwd()
    os.umask(0000)
    cache = os.path.join(cwd, 'tmp')
    if key_id and key_secret and bucket_name:
        s3fs = [bucket_name, mountpoint]
        # s3fs.extend(['-o', 'umask=0000'])
        s3fs.extend(['-o', 'use_cache={cache}'.format(cache=cache)])
        s3fs.extend(['-o', 'del_cache'])
        return s3fs
    return None
