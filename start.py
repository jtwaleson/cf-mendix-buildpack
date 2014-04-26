#!/usr/bin/env python
import json
import os
import re
import signal
import subprocess
import sys
import time
from m2ee import M2EE, logger

logger.setLevel(20)

subprocess.check_call([
    'sed',
    '-i',
    's|BUILD_PATH|%s|g; s|9000|%d|'
    % (os.getcwd(), int(os.environ.get('PORT')) + 1),
    '.local/m2ee.yaml'
])

if os.environ.get('VCAP_APPLICATION'):
    vcap_app = json.loads(os.environ.get('VCAP_APPLICATION'))
else:
    vcap_app = {
        'application_uris': ['example.com'],
        'application_name': 'My App',
    }

if os.environ.get('VCAP_SERVICES'):
    vcap_services = json.loads(os.environ.get('VCAP_SERVICES'))
    if 'newrelic' in vcap_services:
        os.environ['NEW_RELIC_LICENSE_KEY'] = vcap_services['newrelic'][0]['credentials']['licenseKey']


m2ee = M2EE(yamlfiles=['.local/m2ee.yaml'], load_default_files=False)

config = m2ee.config._conf


def sigterm_handler():
    print('stopping the process')
    m2ee.stop()
    print('process stopped')
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)

metadata = json.loads(open('model/metadata.json').read())

constants = {}

for constant in metadata['Constants']:
    env = 'MX_%s' % constant['Name'].replace('.', '_')
    value = os.environ.get(env)
    if value is None:
        value = constant['DefaultValue']
        print(
            'constant not found in environment, taking default '
            'value %s' % constant['Name']
        )
    if constant['Type'] == 'Integer':
        value = int(value)
    constants[constant['Name']] = value

print('using microflow constants')
print(constants)

db_url = os.environ.get('DATABASE_URL')
pattern = r'postgres://([^:]+):([^@]+)@([^/]+)/(.*)'
match = re.search(pattern, db_url)

if match is None:
    raise Exception(
        "Could not parse DATABASE_URL environment variable %s" % db_url
    )
runtime_config = {
    'DatabaseType': 'PostgreSQL',
    'DatabaseUserName': match.group(1),
    'DatabasePassword': match.group(2),
    'DatabaseHost': match.group(3),
    'DatabaseName': match.group(4),
    'ApplicationRootUrl': 'https://%s' % vcap_app['application_uris'][0],
    'MicroflowConstants': constants,
}

for key, value in runtime_config.iteritems():
    config['mxruntime'][key] = value


config['m2ee']['runtime_port'] = int(os.environ.get('PORT'))
config['m2ee']['app_name'] = vcap_app['application_name']

max_memory = os.environ.get('MEMORY_LIMIT', '512m').upper()

match = re.search('([0-9]+)([A-Z])', max_memory)
max_memory = '%d%s' % (int(match.group(1)) / 2, match.group(2))

heap_size = os.environ.get('HEAP_SIZE', max_memory)

javaopts = config['m2ee']['javaopts']

if os.environ.get('NEW_RELIC_LICENSE_KEY'):
    javaopts.append('-javaagent:%s/.local/newrelic-agent.jar' % os.getcwd())
    config['m2ee']['custom_environment']['NEW_RELIC_LICENSE_KEY'] = (
        os.environ.get('NEW_RELIC_LICENSE_KEY')
    )
javaopts.append('-Xmx%s' % heap_size)
javaopts.append('-Xms%s' % heap_size)

print('Java heap size set to %s' % max_memory)

m2ee.start_appcontainer()
if not m2ee.send_runtime_config():
    sys.exit(1)

with open('log/out.log', 'a'):
    os.utime('log/out.log', None)
subprocess.Popen(['tail', '-f', 'log/out.log'])

abort = False
success = False
while not (success or abort):
    startresponse = m2ee.client.start({'autocreatedb': True})
    result = startresponse.get_result()
    if result == 0:
        success = True
        print("The MxRuntime is fully started now.")
    else:
        startresponse.display_error()
        if result == 2:
            print("DB does not exists")
            abort = True
        elif result == 3:
            m2eeresponse = m2ee.client.execute_ddl_commands()
            m2eeresponse.display_error()
        elif result == 4:
            print("Not enough constants!")
            abort = True
        elif result == 5:
            print("Unsafe password!")
            abort = True
        elif result == 6:
            print("Invalid state!")
            abort = True
        elif result == 7 or result == 8 or result == 9:
            print("You'll have to fix the configuration and run start "
                  "again... (or ask for help..)")
            abort = True
        else:
            abort = True
if abort:
    print('start failed, stopping')
    sys.exit(1)

print('Creating admin user')
m2eeresponse = m2ee.client.create_admin_user({
    'password': os.environ.get('ADMIN_PASSWORD'),
})
if m2eeresponse.has_error():
    m2eeresponse.display_error()
    sys.exit(1)

print('Setting admin user password')
m2eeresponse = m2ee.client.create_admin_user({
    'username': metadata['AdminUser'],
    'password': os.environ.get('ADMIN_PASSWORD'),
})
if m2eeresponse.has_error():
    m2eeresponse.display_error()
    sys.exit(1)

feedback = m2ee.client.about().get_feedback()
print("Using %s version %s" % (feedback['name'], feedback['version']))
if m2ee.config.get_runtime_version() >= 4.4:
    if 'model_version' in feedback:
        print('Model version: %s' % feedback['model_version'])

while m2ee.runner.check_pid():
    print('process still alive, sleeping')
    time.sleep(10)

print('process died, stopping')
sys.exit(1)
