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
 - `MOLECULE_MIAREC_SCREEN_VERSION` defines variable `miarec_screen_version`, default `2026.11.15.0`
 - `MOLECULE_ANSIBLE_VERBOSITY` set verbosity for ansible run, like running "ansible -vvv", values 0-3, default 0

## TLS scenario

The `tls` scenario installs PostgreSQL and Redis with TLS in the same container, then installs MiaRec Screen Controller with TLS enabled for both connections, and with client certificates on the control interface, where the screen recording clients connect. The service runs as the `miarec` user and group.

The prepare step generates a test PKI per service on the control machine, in the `tls` directory of `MOLECULE_EPHEMERAL_DIRECTORY`. It needs the `openssl` command there. The CA private keys never leave the control machine. Layout of `tls/<service>/` for `postgresql` and `redis`:

- `ca.crt`: the service's CA certificate
- `client.crt`, `client.key`: client certificate and key for MiaRec
- `server.crt`, `server.key`: server certificate and key

For the control interface, the prepare step generates Screen-CA, which stands for the CA of a deployment, in `tls/screen/`:

- `ca.crt`: the CA certificate of the clients
- `controller.crt`, `controller.key`: the controller's certificate and key, issued for `localhost`
- `client.crt`, `client.key`: a client certificate for the tests

The prepare step uploads the server certificate and the CA certificate to `/etc/postgresql/tls` and `/etc/redis/tls` on the target, and the screen recording client certificate to `/root/screen-client`. The role uploads the client certificate, the client key, and the CA certificate to `/etc/miarec/tls/postgresql` and `/etc/miarec/tls/redis` during converge, the same way the production playbooks do, and the controller's certificate and key, and the CA certificate of the clients, to `/etc/miarec/tls/screen`. Nothing in prepare writes to `/etc/miarec/tls`, so the test proves that the role creates the directories and uploads nine distinct files.

PostgreSQL accepts only `hostssl` connections with a client certificate, and Redis listens only on the TLS port. The tests check that plaintext connections are rejected, so a healthy `/health` response proves that the application uses TLS.

The control interface tests connect to port 6092 with `openssl s_client`, verifying the controller against Screen-CA: a client without a certificate gets the alert `certificate required`, and a client certificate of another CA gets `unknown ca`. The `side_effect` step renews the controller's certificate on the control machine and runs the role again, which must upload it and restart the controller. The tests then check that the controller presents the renewed certificate.

MiaRec Screen Controller 2026.8.3.0 and 2026.10.26.0 crash as soon as they accept a client connection, over TCP or TLS ([ScreenRecController#15](https://github.com/miarecdev/ScreenRecController/issues/15)). The test that connects with a client certificate of Screen-CA checks that the controller keeps running, so the scenario fails with those releases.

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
 - `MOLECULE_MIAREC_SCREEN_VERSION` default `2026.11.15.0`, the first release that accepts client connections without crashing (2026.8.3.0 is the first with TLS to PostgreSQL and Redis)
 - `MOLECULE_MIAREC_SCREEN_BIN_USER`, `MOLECULE_MIAREC_SCREEN_BIN_GROUP` the service user and group, default `miarec`
