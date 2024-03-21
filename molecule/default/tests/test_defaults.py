import os
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