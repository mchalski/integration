import subprocess
import json
import requests
from requests.auth import HTTPBasicAuth
from fabric.api import execute
import helpers

CLIENT = helpers.get_mender_client()

def get_client_id():
    keyres = execute(helpers.get_client_key, hosts=CLIENT)
    idres = execute(helpers.get_client_iddata, hosts=CLIENT)
    return {'device_identity': idres[CLIENT],
            'key': keyres[CLIENT].exportKey() + '\n'}

def new_id_data(id_data_dict):
    execute(helpers.substitute_id_data, id_data_dict, hosts=CLIENT)

def restart():
    execute(helpers.restart, hosts=CLIENT)

def create_user(name, pwd):
    uadm = helpers.docker_get_useradm()
    cmd = 'docker exec {} useradm create-user --username {} --password {}'.format(uadm, name, pwd)
    return subprocess.check_output(cmd, shell=True)

def login(name, pwd):
    r = requests.post("https://localhost/api/management/v1/useradm/auth/login",verify=False, auth=HTTPBasicAuth(name, pwd))
    return r.text

def preauth(device_identity, key, token):
    path = "https://localhost/api/management/v1/admission/devices"
    req = {'device_identity': device_identity, 'key': key}
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + token}

    res = requests.post(path, data=json.dumps(req), headers=headers, verify=False).text
