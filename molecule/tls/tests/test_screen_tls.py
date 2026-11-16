"""TLS on the control interface, where the screen recording clients connect.

prepare.yml (tasks/screen_certificates.yml) generates Screen-CA, the CA of
the deployment, on the control machine, and with it the controller's
certificate for localhost and a client certificate. converge.yml gives the
controller's certificate and key, and the CA certificate, to the role as
miarec_screen_tls_*_src, which uploads them and turns on client certificates
on the TLS port. prepare.yml uploads the client certificate for the tests,
which connect to the controller with `openssl s_client` from inside the
container. side_effect.yml renews the controller's certificate on the control
machine and runs the role again.

MiaRec Screen Controller 2026.8.3.0 and 2026.10.26.0 crash with SIGSEGV in
CWatchDog::RegisterThread as soon as they accept a client connection, over
TCP or TLS, and systemd restarts them 5 seconds later
(https://github.com/miarecdev/ScreenRecController/issues/15). A handshake that the
controller rejects doesn't reach that code, so the tests read the
controller's certificate from a handshake without a client certificate, and
the test of an accepted client runs last, as an expected failure.
"""
import os
import re
import time
from pathlib import Path

import pytest
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')

INI = "/opt/miarec_screen/current/miarec_screen.ini"
# PortTLS of miarec_screen.ini.sample. The role doesn't set it.
PORT = 6092
# The controller's certificate is issued for localhost (tasks/screen_controller_certificate.yml).
CONTROLLER_NAME = "localhost"
# On the host: what converge.yml gives the role.
CERT_DIR = "/etc/miarec/tls/screen"
CERT = f"{CERT_DIR}/controller.crt"
KEY = f"{CERT_DIR}/controller.key"
CA = f"{CERT_DIR}/ca.crt"
# On the control machine: what the role uploads (prepare.yml, side_effect.yml).
SRC_DIR = Path(os.environ["MOLECULE_EPHEMERAL_DIRECTORY"]) / "tls" / "screen"
FIRST_CERT_SRC = SRC_DIR / "controller-first.crt"
# The client certificate of Screen-CA, which prepare.yml uploads for the tests.
CLIENT_CERT = "/root/screen-client/client.crt"
CLIENT_KEY = "/root/screen-client/client.key"
# The PostgreSQL client certificate, which the role uploads. Test-CA-postgresql
# signs it, and the controller doesn't trust that CA on the control interface.
OTHER_CA_CLIENT_CERT = "/etc/miarec/tls/postgresql/client.crt"
OTHER_CA_CLIENT_KEY = "/etc/miarec/tls/postgresql/client.key"
BIN_USER = os.environ.get("MIAREC_SCREEN_BIN_USER", "miarec")
BIN_GROUP = os.environ.get("MIAREC_SCREEN_BIN_GROUP", "miarec")


def network_settings(host):
    content = host.file(INI).content_string
    section = re.search(r"^\[Network\]\n(.*?)(?=^\[)", content, re.M | re.S)
    assert section, f"{INI} has no [Network] section"
    return dict(re.findall(r"^(\w+)\s*=[ \t]*(.*?)[ \t]*$", section.group(1), re.M))


def presented_certificate(host):
    """Return the certificate that the controller presents in a TLS handshake.

    s_client sends no client certificate: with TLS 1.3, the controller
    presents its certificate before it asks for the client's, and the
    rejected handshake doesn't crash the controller (see the module docstring).
    """
    result = host.run(f"openssl s_client -connect 127.0.0.1:{PORT} < /dev/null")
    presented = re.search(
        r"^-----BEGIN CERTIFICATE-----\n.*?^-----END CERTIFICATE-----\n", result.stdout, re.M | re.S)
    assert presented, f"s_client printed no server certificate:\n{result.stdout}"
    return presented.group(0)


def tls_session(host, cert=None, key=None):
    """Open a TLS session to the controller, hold it open, and return the result of s_client.

    s_client verifies the controller's certificate against Screen-CA and
    checks its host name, as a screen recording client of the deployment
    does. With TLS 1.3, the controller checks the client certificate after
    the client ends its handshake, and s_client sees the controller's alert
    only when it reads. So the tests hold the session open for a moment
    instead of checking the handshake alone.
    """
    client = f"-cert {cert} -key {key}" if cert else ""
    # s_client reads until its input ends: the sleep gives the controller time to answer.
    return host.run(
        f"sleep 2 | timeout 15 "
        f"openssl s_client -connect 127.0.0.1:{PORT} -CAfile {CA} "
        f"-verify_hostname {CONTROLLER_NAME} -verify_return_error -quiet -no_ign_eof {client}"
    )


def test_the_role_creates_the_directory_and_the_files_with_their_permissions(host):
    # The role created the directory, so it has the fixed mode, not the umask.
    directory = host.file(CERT_DIR)
    assert directory.is_directory
    assert (directory.user, directory.mode) == ("root", 0o755)

    for path in (CERT, CA):
        certificate = host.file(path)
        assert certificate.is_file
        assert (certificate.user, certificate.mode) == ("root", 0o644), path

    key = host.file(KEY)
    assert key.is_file
    assert (key.user, key.group, key.mode) == ("root", BIN_GROUP, 0o640)


def test_the_ca_key_is_not_on_the_host(host):
    assert not host.file(f"{CERT_DIR}/ca.key").exists


def test_the_role_uploads_the_files_from_the_control_machine(host):
    for path, name in ((CERT, "controller.crt"), (KEY, "controller.key"), (CA, "ca.crt")):
        assert host.file(path).content_string == (SRC_DIR / name).read_text(), path


def test_the_service_user_can_read_the_key(host):
    """The service user reads the private key through miarec_screen_bin_group."""
    result = host.run(f"runuser -u {BIN_USER} -- cat {KEY}")
    assert result.rc == 0, f"{BIN_USER} cannot read {KEY}: {result.stderr}"


def test_miarec_screen_ini_has_the_control_interface_tls_settings(host):
    settings = network_settings(host)
    assert settings["SSLCertificate"] == CERT
    assert settings["SSLPrivateKey"] == KEY
    assert settings["SSLCACertificates"] == CA


def test_the_controller_does_not_create_a_certificate_of_its_own(host):
    """With the role's files in place, the controller doesn't write the sample's files."""
    for name in ("screen_rec_cert.pem", "screen_rec_pkey.pem"):
        assert not host.file(f"/opt/miarec_screen/shared/{name}").exists, name


def test_the_controller_listens_on_the_tls_port(host):
    assert host.socket(f"tcp://0.0.0.0:{PORT}").is_listening


def test_the_controller_presents_the_renewed_certificate(host):
    """side_effect.yml renewed the certificate on the control machine and ran the role again."""
    renewed = (SRC_DIR / "controller.crt").read_text()
    assert renewed != FIRST_CERT_SRC.read_text()
    assert host.file(CERT).content_string == renewed
    assert presented_certificate(host) == renewed


def test_the_controller_refuses_a_client_without_a_certificate(host):
    result = tls_session(host)
    assert result.rc != 0
    assert "alert certificate required" in result.stderr


def test_the_controller_refuses_a_client_certificate_of_another_ca(host):
    result = tls_session(host, OTHER_CA_CLIENT_CERT, OTHER_CA_CLIENT_KEY)
    assert result.rc != 0
    assert "alert unknown ca" in result.stderr


def wait_for_the_controller(host):
    """Wait until the controller runs and listens on the TLS port again.

    The accepted connection crashes the controller (see the module
    docstring), and systemd restarts it 5 seconds later. The tests of
    test_tls.py run after this file and need the service.
    """
    for _ in range(30):
        if host.service("miarec_screen").is_running and host.socket(f"tcp://0.0.0.0:{PORT}").is_listening:
            return
        time.sleep(1)
    raise AssertionError("The controller didn't come back after the accepted connection")


# This test runs last in this file. When a release accepts the client, the
# test passes, and the strict marker fails the run, so that the marker gets
# removed.
@pytest.mark.xfail(
    strict=True,
    reason="MiaRec Screen Controller 2026.8.3.0 and 2026.10.26.0 crash on an accepted connection, "
    "see https://github.com/miarecdev/ScreenRecController/issues/15",
)
def test_the_controller_accepts_a_client_with_a_certificate_of_the_client_ca(host):
    try:
        result = tls_session(host, CLIENT_CERT, CLIENT_KEY)
    finally:
        wait_for_the_controller(host)
    assert result.rc == 0, result.stdout + result.stderr
    assert "alert" not in result.stderr, result.stderr
