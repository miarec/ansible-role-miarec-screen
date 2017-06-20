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




