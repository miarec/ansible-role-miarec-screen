# Molecule test this role

Run Molecule test
```
molecule test
```

Run test with variable example
```
MOLECULE_DISTRO=centos7 MOLECULE_MIAREC_SCREEN_VERSION=1.1.0.46 molecule test
```

## Variables
 - `MOLECULE_DISTRO` OS of docker container to test, default `ubuntu2204`
    List of tested distros
    - `ubuntu2204`
    - `ubuntu2004`
    - `centos7`
    - `rockylinux9`
    - `rockylinux8`
    - `rhel9`
    - `rhel8`
    - `rhel7`
 - `MOLECULE_MIAREC_SCREEN_VERSION` defines variable `miarec_screen_version`, default `2024.4.5.0`
 - `MOLECULE_ANSIBLE_VERBOSITY` set verbosity for ansible run, like running "ansible -vvv", values 0-3, default 0

## TLS scenario

The `tls` scenario installs PostgreSQL and Redis with TLS in the same container, then installs MiaRec Screen Controller with TLS enabled for both connections. The service runs as the `miarec` user and group.

The prepare step generates the test certificates on the control machine, in the `tls` directory of `MOLECULE_EPHEMERAL_DIRECTORY`. It needs the `openssl` command there. The CA private key never leaves the control machine.

- `ca.crt`: CA certificate that signs all other certificates
- `client.crt`, `client.key`: client certificate and key for MiaRec
- `postgresql/server.crt`, `postgresql/server.key`: PostgreSQL server certificate and key
- `redis/server.crt`, `redis/server.key`: Redis server certificate and key

The prepare step uploads the server certificates and the CA certificate to `/etc/postgresql/tls` and `/etc/redis/tls` on the target. The role uploads the client certificate, the client key, and the CA certificate to `/etc/miarec/tls` during converge, the same way the production playbooks do. Nothing in prepare writes to `/etc/miarec/tls`, so the test proves the role's upload.

PostgreSQL accepts only `hostssl` connections with a client certificate, and Redis listens only on the TLS port. The tests check that plaintext connections are rejected, so a healthy `/health` response proves that the application uses TLS.

Run the TLS scenario
```
MOLECULE_DISTRO=rockylinux9 uv run molecule test -s tls
```

The converge playbook refers to the role as `ansible-role-miarec-screen` and looks for it in the parent directory of the project. When the role directory has a different name, for example in a git submodule, point Molecule to a symbolic link with the expected name:
```
mkdir -p /tmp/roles && ln -sfn "$PWD" /tmp/roles/ansible-role-miarec-screen
cd /tmp/roles/ansible-role-miarec-screen
MOLECULE_PROJECT_DIRECTORY=/tmp/roles/ansible-role-miarec-screen uv run molecule test -s tls
```

To run several distros in parallel, give each run its own `MOLECULE_EPHEMERAL_DIRECTORY`.

TLS scenario variables:
 - `MOLECULE_MIAREC_SCREEN_VERSION` default `2026.8.3.0`, the first release with TLS support
 - `MOLECULE_MIAREC_SCREEN_BIN_USER`, `MOLECULE_MIAREC_SCREEN_BIN_GROUP` the service user and group, default `miarec`
