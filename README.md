# ansible-role-miarec-screen

Ansible role for installing of MiaRec Screen Controller application.


Role Variables
--------------

- `miarec_screen_version`: The version of miarec screen files to install
- `miarec_screen_instance_name`: The instance name (default: Recorder). Multiple recorder instances could connect to the same database. Using the unique name for each instance allows to configure each instance individually.
- `miarec_screen_install_dir`: The installation directory (default: /opt/miarec_screen)
- `miarec_screen_log_dir`: The location of log files (default: /var/log/miarec_screen)
- `miarec_db_host`: The PostgreSQL host (default: 127.0.0.1)
- `miarec_db_port`: The PostgreSQL port (default: 5432)
- `miarec_db_name`: The PostgreSQL database name (default: miarecdb)
- `miarec_db_user`: The ostgreSQL database user (default: miarec)
- `miarec_db_password`: The PostgreSQL database password (default: password)
- `miarec_redis_host`: The Redis host (default: 127.0.0.1)
- `miarec_redis_port`: The Redis port (default: 6379)
- `miarec_screen_bin_user`, `miarec_screen_bin_group`: The user and group that run the service (default: root)

### TLS for PostgreSQL and Redis

MiaRec Screen Controller 2026.8.3.0 and later can connect to PostgreSQL and Redis over TLS. TLS is off by default.

The role always writes `UseSSL` from the matching `*_use_ssl` variable, so disabling TLS takes effect on the next run. The role writes the other TLS settings to `miarec_screen.ini` only when `*_use_ssl` is `true`. The role uploads a certificate file from the Ansible control machine when its `*_src` variable is set. Otherwise the file must exist on the host before the role runs. The role sets permissions only on the files it uploads. A missing parent directory is created as `0755` owned by root, and an existing directory is left alone, because it may be shared with other services. Before the release is finalized, the role checks that `miarec_screen_bin_user` can read every TLS file in use, uploaded or not, and fails the play with the file named when it cannot.

PostgreSQL variables, written to the `[Database]` section. This section covers the configuration loader, the SQL event log and the SQL errors log.

- `miarec_db_use_ssl`: Connect to PostgreSQL over TLS (default: false). Sets `UseSSL`.
- `miarec_db_tls_ca_file`: The CA certificate that validates the server certificate (default: empty). Sets `SSLCACertificates`.
- `miarec_db_tls_cert_file`: The client certificate for mutual TLS (default: empty). Sets `SSLCertificate`.
- `miarec_db_tls_key_file`: The client private key for mutual TLS (default: empty). Sets `SSLPrivateKey`.
- `miarec_db_tls_check_hostname`: Verify the server host name against its certificate (default: false). Sets `CheckHostName`.
- `miarec_db_tls_ca_file_src`, `miarec_db_tls_cert_file_src`, `miarec_db_tls_key_file_src`: Local copies of the files above (default: empty). When set, the role uploads the file to the matching path, owned by root with mode 0644 for certificates and 0640 for the key, and restarts the service when the file changed.

The application derives the libpq `sslmode`: `require` without a CA file, `verify-ca` with a CA file, and `verify-full` with a CA file and `miarec_db_tls_check_hostname: true`.

Redis variables, written to the `[RedisSubscriber]` section:

- `miarec_redis_use_ssl`: Connect to Redis over TLS (default: false). Sets `UseSSL`.
- `miarec_redis_tls_ca_file`: The CA certificate that validates the server certificate (default: empty). Sets `SSLCACertificates`.
- `miarec_redis_tls_cert_file`: The client certificate (default: empty). Sets `SSLCertificate`. Required when `miarec_redis_use_ssl` is true.
- `miarec_redis_tls_key_file`: The client private key (default: empty). Sets `SSLPrivateKey`. Required when `miarec_redis_use_ssl` is true.
- `miarec_redis_tls_check_hostname`: Verify the server host name against its certificate (default: false). Sets `CheckHostName`.
- `miarec_redis_tls_ca_file_src`, `miarec_redis_tls_cert_file_src`, `miarec_redis_tls_key_file_src`: Local copies of the files above (default: empty), see `miarec_db_tls_*_src`.

The application refuses Redis TLS without a client certificate and key, so the role fails early when `miarec_redis_use_ssl` is true and either file is not set.

The REST API reports the connection state at `http://<host>:6089/health`. The response is JSON with `status`, `database` and `redis` fields, each `ok`, `error` or `disabled`.

### TLS on the control interface

The screen recording clients connect to the controller on the TLS port of the `[Network]` section, `PortTLS`, which is 6092 in the sample configuration file. The role doesn't set the port. These variables set the TLS files of that section:

- `miarec_screen_tls_cert_file`: The path of the controller's certificate on the host (default: empty). Sets `SSLCertificate`. Set it with the key.
- `miarec_screen_tls_key_file`: The path of the controller's private key on the host (default: empty). Sets `SSLPrivateKey`. Set it with the certificate.
- `miarec_screen_tls_ca_file`: The path of a PEM file on the host with the CA certificates of the clients (default: empty). Sets `SSLCACertificates`. Set it to require client certificates.
- `miarec_screen_tls_cert_file_src`, `miarec_screen_tls_key_file_src`, `miarec_screen_tls_ca_file_src`: Local copies of the files above (default: empty), see `miarec_db_tls_*_src`.

The role writes the three file settings when any of the paths is set, and restarts the controller when a setting or an uploaded file changed. With no path set, the default, the role leaves the `[Network]` section alone. The sample configuration file then names `screen_rec_cert.pem` and `screen_rec_pkey.pem`, relative to `miarec_screen_work_dir`, and the controller creates a self-signed certificate under these names at startup when they don't exist.

The controller's certificate comes from the CA of your deployment, as the PostgreSQL and Redis client certificates do: the role doesn't create or sign certificates. Put the certificate and the key on the Ansible control machine and set `miarec_screen_tls_cert_file_src` and `miarec_screen_tls_key_file_src`, and the role uploads them as it uploads the PostgreSQL and Redis files: owner root, group `miarec_screen_bin_group`, mode 0644 for the certificate and 0640 for the key. When a file changed, the role restarts the controller, so a renewed certificate takes effect with the next run. When a `*_src` variable is empty, the file must already be on the host, and the role leaves its permissions as they are. Before the release is finalized, the role checks that `miarec_screen_bin_user` can read every file in use, uploaded or not.

Set the certificate and the key together, or neither, or the role fails. A client that verifies or pins the controller's certificate can't know a self-signed certificate before the controller starts, and that certificate changes whenever its files are lost.

When `miarec_screen_tls_ca_file` is set, the controller requires a client certificate signed by one of the CA certificates in that file, and refuses a client without one. When it's empty, the controller doesn't ask for a client certificate. If a client certificate has an extended key usage extension, it must include `clientAuth`.

The settings of the `[Network]` section that the MiaRec web portal stores in the database take precedence over `miarec_screen.ini`, which is the fallback. If the web portal sets any of these settings for a controller, the controller uses the value from the database, and the role's value has no effect.

Example Playbook
----------------

eg:

``` yaml
    - name: Install miarec screen recorder
      hosts: localhost
      become: yes
      roles:
        - role: ansible-role-miarec-screen
          miarec_screen_version: 1.1.0.11 
```

The above playbook will install miarec screen version 1.1.0.11.

Example with TLS for PostgreSQL and Redis:

``` yaml
    - name: Install miarec screen recorder
      hosts: screen
      become: yes
      roles:
        - role: ansible-role-miarec-screen
          miarec_screen_version: 2026.8.3.0
          miarec_screen_bin_user: miarec
          miarec_screen_bin_group: miarec
          miarec_db_use_ssl: true
          miarec_db_tls_ca_file: /etc/miarec/tls/ca.crt
          miarec_db_tls_cert_file: /etc/miarec/tls/client.crt
          miarec_db_tls_key_file: /etc/miarec/tls/client.key
          miarec_redis_use_ssl: true
          miarec_redis_tls_ca_file: /etc/miarec/tls/ca.crt
          miarec_redis_tls_cert_file: /etc/miarec/tls/client.crt
          miarec_redis_tls_key_file: /etc/miarec/tls/client.key
```

Example with TLS on the control interface, with client certificates. The role uploads the files from the control machine:

``` yaml
    - name: Install miarec screen recorder
      hosts: screen
      become: yes
      roles:
        - role: ansible-role-miarec-screen
          miarec_screen_version: 2026.8.3.0
          miarec_screen_bin_user: miarec
          miarec_screen_bin_group: miarec
          miarec_screen_tls_cert_file: /etc/miarec/tls/screen/controller.crt
          miarec_screen_tls_key_file: /etc/miarec/tls/screen/controller.key
          miarec_screen_tls_ca_file: /etc/miarec/tls/screen/ca.crt
          miarec_screen_tls_cert_file_src: files/tls/screen/controller.crt
          miarec_screen_tls_key_file_src: files/tls/screen/controller.key
          miarec_screen_tls_ca_file_src: files/tls/screen/ca.crt
```

## Testing

This role uses [Molecule](https://molecule.readthedocs.io/) with Docker for testing.
[uv](https://docs.astral.sh/uv/) is used for dependency management.

### Prerequisites

- Docker
- uv (install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Running Tests

```bash
# Run the default scenario
uv run molecule test

# Run the TLS scenario
uv run molecule test -s tls

# Test against a specific distro
MOLECULE_DISTRO=ubuntu2404 uv run molecule test
MOLECULE_DISTRO=rockylinux9 uv run molecule test
```

### Available Distros

| Distribution   | Variable Value  |
|----------------|-----------------|
| Ubuntu 22.04   | `ubuntu2204`    |
| Ubuntu 24.04   | `ubuntu2404`    |
| Rocky Linux 9  | `rockylinux9`   |
| RHEL 9         | `rhel9`         |

### Linting

```bash
uv run ansible-lint
```
