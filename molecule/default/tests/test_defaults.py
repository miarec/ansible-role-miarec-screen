import os
import re
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')

miarec_screen_version = os.environ.get('MIAREC_SCREEN_VERSION')


def test_directories(host):

    dirs = [
        "/opt/miarec_screen/releases/{}".format(miarec_screen_version),
        "/opt/miarec_screen/shared",
        "/var/log/miarec_screen",
        "/var/log/miarec_screen/error",
        "/var/log/miarec_screen/trace"
    ]
    for dir in dirs:
        d = host.file(dir)
        assert d.is_directory
        assert d.exists

def test_files(host):
    files = [
        "/opt/miarec_screen/releases/{}/miarec_screen".format(miarec_screen_version),
        "/opt/miarec_screen/releases/{}/miarec_screen.ini".format(miarec_screen_version),
    ]

    for file in files:
        f = host.file(file)
        assert f.exists
        assert f.is_file

def test_service(host):
    services = [
        "miarec_screen"
    ]

    for service in services:
        s = host.service(service)
        assert s.is_enabled
        assert s.is_running

def test_socket(host):
    sockets = [
        "tcp://0.0.0.0:6091",
        "tcp://0.0.0.0:6092"
    ]
    for socket in sockets:
        s = host.socket(socket)
        assert s.is_listening


def test_control_interface_tls_keeps_the_sample_files(host):
    """By default, the role leaves the [Network] TLS settings of the sample file alone.

    The controller then creates a self-signed certificate of its own in the
    working directory at startup.
    """
    content = host.file("/opt/miarec_screen/current/miarec_screen.ini").content_string
    section = re.search(r"^\[Network\]\n(.*?)(?=^\[)", content, re.M | re.S)
    assert section, "miarec_screen.ini has no [Network] section"
    settings = dict(re.findall(r"^(\w+)\s*=[ \t]*(.*?)[ \t]*$", section.group(1), re.M))
    assert settings["SSLCertificate"] == "screen_rec_cert.pem"
    assert settings["SSLPrivateKey"] == "screen_rec_pkey.pem"
    assert settings["SSLCACertificates"] == ""
    for name in ("screen_rec_cert.pem", "screen_rec_pkey.pem"):
        assert host.file(f"/opt/miarec_screen/shared/{name}").is_file, name
