# Copyright 2018 Northern.tech AS
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        https://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import infra.docker as docker

class CliUseradm:
    def __init__(self):
        self.cid = docker.getid('mender-useradm')

        # is it an open useradm, or useradm-enterprise?
        for path in ['/usr/bin/useradm', '/usr/bin/useradm-enterprise']:
            try: 
                docker.exec(self.cid, [path, '--version'])
                self.path=path
            except:
                continue

        if self.path is None:
            raise RuntimeError('no runnable binary found in mender-useradm')

    def create_user(self, username, password, tenant_id=''):
        cmd = [self.path,
               'create-user',
               '--username', username,
               '--password', password]

        if tenant_id != '':
            cmd += ['--tenant-id', tenant_id]

        uid=docker.exec(self.cid, cmd)
        return uid

    def migrate(self, tenant_id=None):
        cmd = [self.path,
               'migrate']

        if tenant_id is not None:
            cmd.extend(['--tenant', tenant_id])

        docker.exec(self.cid, cmd)


class CliTenantadm:
    def __init__(self):
        self.cid = docker.getid('mender-tenantadm')

    def create_tenant(self, name):
        cmd = ['/usr/bin/tenantadm',
               'create-tenant',
               '--name', name]

        tid = docker.exec(self.cid, cmd)
        return tid

    def migrate(self):
        cmd = ['usr/bin/tenantadm',
               'migrate']

        docker.exec(self.cid, cmd)

class CliDeviceauth:
    def __init__(self):
        self.cid = docker.getid('mender-device-auth')

    def migrate(self, tenant_id=None):
        cmd = ['usr/bin/deviceauth',
               'migrate']

        if tenant_id is not None:
            cmd.extend(['--tenant', tenant_id])

        docker.exec(self.cid, cmd)
