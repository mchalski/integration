import subprocess
from Crypto.PublicKey import RSA
from fabric.api import run, env

PRIV_KEY = '/data/mender/mender-agent.pem'
ID_HELPER = '/usr/share/mender/identity/mender-device-identity'

env.password = ""

def get_mender_client():
    cmd = "docker ps -q " \
           "--filter label=com.docker.compose.service=mender-client"

    output = subprocess.check_output(cmd + \
                                     "| xargs -r " \
                                     "docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'",
                                     shell=True)

    return "root@" +output.split()[0] + ":8822"

def get_client_key():
    keystr = run('cat {}'.format(PRIV_KEY))
    key = RSA.importKey(keystr)
    return key.publickey()

def get_client_iddata():
    return run(ID_HELPER, stderr=None)

def create_user(name, pwd):
    uadm = docker_get_useradm()
    cmd = 'docker exec {} useradm create-user --username {} --password {}'.format(uadm, name, pwd)
    return subprocess.check_output(cmd, shell=True)

def docker_get_useradm():
    cmd = 'docker ps | grep mender-useradm | awk \'{print $1}\''
    return subprocess.check_output(cmd, shell=True).rstrip()

def substitute_id_data(id_data_dict):
    id_data = '#!/bin/sh\n'
    for k,v in id_data_dict.items():
        id_data += 'echo {}={}\n'.format(k,v)

    cmd = 'echo "{}" > {}'.format(id_data, ID_HELPER)
    run(cmd)

def restart():
    run('systemctl restart mender.service')
