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

TLS_OPTIONS = {
    'UseSSL': 'true',
    'SSLCACertificates': '/etc/miarec/tls/ca.crt',
    'SSLCertificate': '/etc/miarec/tls/client.crt',
    'SSLPrivateKey': '/etc/miarec/tls/client.key',
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
    for option, expected in TLS_OPTIONS.items():
        assert values.get(option) == expected, f"[Database] {option}: {values.get(option)!r}"


def test_miarec_screen_ini_has_redis_tls_settings(host):
    """Test that the [RedisSubscriber] section contains TLS settings."""
    content = host.file(INI_FILE).content_string
    values = read_ini_section(content, 'RedisSubscriber')
    for option, expected in TLS_OPTIONS.items():
        assert values.get(option) == expected, f"[RedisSubscriber] {option}: {values.get(option)!r}"


def test_tls_certificate_files_exist(host):
    """Test that TLS certificate files exist with correct permissions."""
    ca_file = host.file('/etc/miarec/tls/ca.crt')
    assert ca_file.exists
    assert ca_file.mode == 0o644

    client_cert = host.file('/etc/miarec/tls/client.crt')
    assert client_cert.exists
    assert client_cert.mode == 0o644

    client_key = host.file('/etc/miarec/tls/client.key')
    assert client_key.exists
    assert client_key.mode == 0o640
    assert client_key.group == BIN_GROUP


def test_postgresql_tls_connection(host):
    """Test that PostgreSQL TLS connection works."""
    cmd = host.run(
        'psql "host=127.0.0.1 port=5432 dbname=miarecdb user=miarec password=password '
        'sslmode=verify-ca '
        'sslrootcert=/etc/miarec/tls/ca.crt '
        'sslcert=/etc/miarec/tls/client.crt '
        'sslkey=/etc/miarec/tls/client.key" '
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
        '--cacert /etc/miarec/tls/ca.crt '
        '--cert /etc/miarec/tls/client.crt '
        '--key /etc/miarec/tls/client.key '
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
