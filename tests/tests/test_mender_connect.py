# Copyright 2020 Northern.tech AS
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

import logging
import pytest
import time

from testutils.api import proto_shell, protomsg
from ..common_setup import class_persistent_standard_setup_one_client_bootstrapped
from ..MenderAPI import devconnect


class TestMenderConnect:
    def test_regular_protocol_commands(
        self, class_persistent_standard_setup_one_client_bootstrapped
    ):
        device = class_persistent_standard_setup_one_client_bootstrapped.device

        with devconnect.get_websocket() as ws:
            # Start shell.
            shell = proto_shell.ProtoShell(ws)
            body = shell.startShell()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL
            assert body == b"Shell started"

            # Drain any initial output from the prompt. It should end in either "# "
            # (root) or "$ " (user).
            output = shell.recvOutput()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL
            assert output[-2:].decode() in [
                "# ",
                "$ ",
            ], "Could not detect shell prompt."

            # Starting the shell again should be a no-op. It should return that
            # it is already started, as long as the shell limit is 1. MEN-4240.
            body = shell.startShell()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_ERROR
            assert body == b"failed to start shell: shell is already running"

            # Make sure we do not get any new output, it should be the same shell as before.
            output = shell.recvOutput()
            assert (
                output == b""
            ), "Unexpected output received when relauncing already launched shell."

            # Test if a simple command works.
            shell.sendInput("ls /\n".encode())
            output = shell.recvOutput()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL
            output = output.decode()
            assert "usr" in output
            assert "etc" in output

            # Try to stop shell.
            body = shell.stopShell()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL
            assert body is None

            # Repeat stopping and verify the error
            body = shell.stopShell()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_ERROR
            assert b"session not found" in body, body

            # Make sure we can not send anything to the shell.
            shell.sendInput("ls /\n".encode())
            output = shell.recvOutput()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_ERROR
            output = output.decode()
            assert "usr" not in output
            assert "etc" not in output
            assert "session not found" in output, output

            # Start it again.
            shell.startShell()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL

            # Drain any initial output from the prompt. It should end in either "# "
            # (root) or "$ " (user).
            output = shell.recvOutput()
            assert shell.protomsg.props["status"] == protomsg.PROP_STATUS_NORMAL
            assert output[-2:].decode() in [
                "# ",
                "$ ",
            ], "Could not detect shell prompt."

    def test_dbus_reconnect(
        self, class_persistent_standard_setup_one_client_bootstrapped
    ):
        device = class_persistent_standard_setup_one_client_bootstrapped.device

        with devconnect.get_websocket() as ws:
            # Nothing to do, just connecting successfully is enough.
            pass

        # Test that mender-connect recovers if it initially has no DBus
        # connection. This is important because we don't have DBus activation
        # enabled in the systemd service file, so it's a race condition who gets
        # to the DBus service first.
        device.run("systemctl --job-mode=ignore-dependencies stop mender-client")
        device.run("systemctl --job-mode=ignore-dependencies restart mender-connect")

        time.sleep(10)

        # At this point, mender-connect will already have queried DBus.
        device.run("systemctl --job-mode=ignore-dependencies start mender-client")

        with devconnect.get_websocket() as ws:
            # Nothing to do, just connecting successfully is enough.
            pass

    def test_websocket_reconnect(
        self, class_persistent_standard_setup_one_client_bootstrapped
    ):
        device = class_persistent_standard_setup_one_client_bootstrapped.device

        with devconnect.get_websocket() as ws:
            # Nothing to do, just connecting successfully is enough.
            pass

        # Test that mender-connect recovers if it loses the connection to deviceconnect.
        class_persistent_standard_setup_one_client_bootstrapped.restart_service(
            "mender-deviceconnect"
        )

        time.sleep(10)

        with devconnect.get_websocket() as ws:
            # Nothing to do, just connecting successfully is enough.
            pass

    def test_bogus_shell_message(
        self, class_persistent_standard_setup_one_client_bootstrapped
    ):

        with devconnect.get_websocket() as ws:
            prot = protomsg.ProtoMsg(proto_shell.PROTO_TYPE_SHELL)

            prot.clear()
            prot.setTyp("bogusmessage")
            msg = prot.encode(b"")
            ws.send(msg)

            msg = ws.recv()
            body = prot.decode(msg)
            assert prot.props["status"] == protomsg.PROP_STATUS_ERROR
            assert prot.protoType == proto_shell.PROTO_TYPE_SHELL
            assert prot.typ == "bogusmessage"

    def test_bogus_proto_message(
        self, class_persistent_standard_setup_one_client_bootstrapped
    ):

        with devconnect.get_websocket() as ws:
            prot = protomsg.ProtoMsg(12345)

            prot.clear()
            prot.setTyp(proto_shell.MSG_TYPE_SPAWN_SHELL)
            msg = prot.encode(b"")
            ws.send(msg)

            msg = ws.recv()
            body = prot.decode(msg)
            assert prot.props["status"] == protomsg.PROP_STATUS_ERROR
            assert prot.protoType == 12345
            assert prot.typ == proto_shell.MSG_TYPE_SPAWN_SHELL
