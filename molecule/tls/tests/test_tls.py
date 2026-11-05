"""Test TLS configuration for MiaRec Screen Controller."""
import json
import os
import time

import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']
).get_hosts('all')

INI_FILE = '/opt/miarec_screen/current/miarec_screen.ini'
BIN_USER = os.environ.get('MIAREC_SCREEN_BIN_USER', 'miarec')
BIN_GROUP = os.environ.get('MIAREC_SCREEN_BIN_GROUP', 'miarec')

# PostgreSQL and Redis each have their own PKI. The role uploads the client
# files into a directory per service.
SERVICES = ('postgresql', 'redis')
TLS_DIR = '/etc/miarec/tls'


def tls_options(service):
    """Return the TLS settings the role writes for one service."""
    return {
        'UseSSL': 'true',
        'SSLCACertificates': f'{TLS_DIR}/{service}/ca.crt',
        'SSLCertificate': f'{TLS_DIR}/{service}/client.crt',
        'SSLPrivateKey': f'{TLS_DIR}/{service}/client.key',
        'CheckHostName': 'false',
    }


def read_ini_section(content, section):
    """Return the key/value pairs of one INI section, skipping comments."""
    values = {}
    current = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line[1:-1]
            continue
        if current == section and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def test_miarec_screen_service_running(host):
    """Test that miarec_screen service is running as the dedicated user."""
    service = host.service('miarec_screen')
    assert service.is_running
    assert service.is_enabled

    process = host.process.get(comm='miarec_screen')
    assert process.user == BIN_USER
    assert process.group == BIN_GROUP


def test_miarec_screen_ini_permissions(host):
    """Test that the service group can read miarec_screen.ini."""
    ini_file = host.file(INI_FILE)
    assert ini_file.exists
    assert ini_file.user == 'root'
    assert ini_file.group == BIN_GROUP
    assert ini_file.mode == 0o640


def test_miarec_screen_ini_has_database_tls_settings(host):
    """Test that the [Database] section contains TLS settings."""
    content = host.file(INI_FILE).content_string
    values = read_ini_section(content, 'Database')
    for option, expected in tls_options('postgresql').items():
        assert values.get(option) == expected, f"[Database] {option}: {values.get(option)!r}"


def test_miarec_screen_ini_has_redis_tls_settings(host):
    """Test that the [RedisSubscriber] section contains TLS settings."""
    content = host.file(INI_FILE).content_string
    values = read_ini_section(content, 'RedisSubscriber')
    for option, expected in tls_options('redis').items():
        assert values.get(option) == expected, f"[RedisSubscriber] {option}: {values.get(option)!r}"


def test_tls_file_permissions(host):
    """The role uploads the private keys readable by the service group only."""
    for svc in SERVICES:
        key = host.file(f'{TLS_DIR}/{svc}/client.key')
        assert key.is_file, f"{svc} key is missing"
        assert key.user == 'root', f"{svc} key is not owned by root"
        assert key.group == BIN_GROUP, f"{svc} key is not group {BIN_GROUP}"
        assert key.mode == 0o640, f"{svc} key is not 0640"
        for name in ('ca.crt', 'client.crt'):
            cert = host.file(f'{TLS_DIR}/{svc}/{name}')
            assert cert.is_file, f"{svc}/{name} is missing"
            assert cert.user == 'root', f"{svc}/{name} is not owned by root"
            assert cert.mode == 0o644, f"{svc}/{name} is not 0644"
        # The role created the directory, so it has the fixed mode, not the umask.
        tls_dir = host.file(f'{TLS_DIR}/{svc}')
        assert tls_dir.user == 'root', f"{svc} directory is not owned by root"
        assert tls_dir.mode == 0o755, f"{svc} directory is not 0755"


def test_ca_key_not_on_host(host):
    """The CA private keys stay on the control machine."""
    for svc in SERVICES:
        assert not host.file(f'{TLS_DIR}/{svc}/ca.key').exists


def test_service_user_can_read_tls_keys(host):
    """The service user reads the private keys through the service group."""
    for svc in SERVICES:
        result = host.run(f'runuser -u {BIN_USER} -- cat {TLS_DIR}/{svc}/client.key')
        assert result.rc == 0, f"{BIN_USER} cannot read {svc} client.key: {result.stderr}"


def test_postgresql_tls_connection(host):
    """Test that PostgreSQL TLS connection works."""
    cmd = host.run(
        'psql "host=127.0.0.1 port=5432 dbname=miarecdb user=miarec password=password '
        'sslmode=verify-ca '
        f'sslrootcert={TLS_DIR}/postgresql/ca.crt '
        f'sslcert={TLS_DIR}/postgresql/client.crt '
        f'sslkey={TLS_DIR}/postgresql/client.key" '
        '-c "SELECT 1;"'
    )
    assert cmd.rc == 0, cmd.stderr


def test_postgresql_rejects_plaintext_connection(host):
    """Test that PostgreSQL rejects connections without TLS."""
    cmd = host.run(
        'psql "host=127.0.0.1 port=5432 dbname=miarecdb user=miarec password=password '
        'sslmode=disable" -c "SELECT 1;"'
    )
    assert cmd.rc != 0
    # PostgreSQL 13 says "SSL off", PostgreSQL 16 says "no encryption"
    assert 'pg_hba.conf rejects connection' in cmd.stderr, cmd.stderr


def test_redis_tls_connection(host):
    """Test that Redis TLS connection works."""
    cmd = host.run(
        'redis-cli --tls '
        f'--cacert {TLS_DIR}/redis/ca.crt '
        f'--cert {TLS_DIR}/redis/client.crt '
        f'--key {TLS_DIR}/redis/client.key '
        '-h 127.0.0.1 -p 6379 PING'
    )
    assert cmd.rc == 0
    assert 'PONG' in cmd.stdout


def test_redis_rejects_plaintext_connection(host):
    """Test that Redis rejects connections without TLS."""
    cmd = host.run('timeout 10 redis-cli -h 127.0.0.1 -p 6379 PING')
    assert 'PONG' not in cmd.stdout, cmd.stdout


def test_health_endpoint(host):
    """Verify /health reports database and redis as ok over TLS.

    PostgreSQL and Redis accept TLS connections only, so "ok" proves that
    the application connects over TLS.
    """
    # The /health endpoint allows 10 requests per minute from one IP address.
    # Poll slowly while the service connects to PostgreSQL and Redis.
    payload = None
    for _ in range(8):
        result = host.run("curl -sS http://127.0.0.1:6089/health")
        if result.rc == 0:
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"Health endpoint response is not valid JSON: {exc}\n"
                    f"Response: {result.stdout}"
                )
            if payload.get("status") == "ok":
                break
        time.sleep(5)

    assert payload is not None, f"Health endpoint not reachable: {result.stderr}"
    assert payload.get("status") == "ok", f"Unexpected overall status: {payload}"
    assert payload.get("database") == "ok", f"Database TLS connection failed: {payload}"
    assert payload.get("redis") == "ok", f"Redis TLS connection failed: {payload}"


def test_postgresql_sessions_use_tls(host):
    """Test that every application session in PostgreSQL uses TLS."""
    cmd = host.run(
        'runuser -u postgres -- psql -tA -d miarecdb -c %s',
        "SELECT s.ssl FROM pg_stat_activity a JOIN pg_stat_ssl s USING (pid) "
        "WHERE a.usename = 'miarec'",
    )
    assert cmd.rc == 0, cmd.stderr
    sessions = cmd.stdout.split()
    assert sessions, "No miarec sessions in pg_stat_activity"
    assert all(ssl == 't' for ssl in sessions), cmd.stdout
