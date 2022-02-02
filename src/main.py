#!/bin/env python3

import paramiko
import kubernetes
from secrets import choice
import yaml
import string
import os
import sys


def random(N=64):
    return ''.join([choice(string.ascii_lowercase +
                           string.ascii_uppercase + string.digits) for _ in range(N)])


def execute_ssh(ssh, cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    err = stderr.read()
    if err != "":
        print(f"Error in ssh command: {err}")
        exit(1)
    return stdout


def execute_kubectl(k8s, cmd):
    k8s.write_stdin(cmd + "\n")
    err = k8s.read_stderr()
    if err != "":
        print(f"Error in kubectl command: {err}")
        exit(1)
    return k8s.read_stdout(timeout=3)


def execute(channel, fun, commands, owncloud_host_hostname_command, owncloud_host_config_command):
    for cmd in commands:
        print(f"Running command: {cmd}\n")
        fun(channel, cmd)

    # via php hostname
    owncloud_url = fun(channel, owncloud_host_hostname_command)

    # via overwrites from config
    for overwrite in fun(channel, owncloud_host_config_command):
        # remove comma, because we look at php dict parts
        overwrite = overwrite.replace(",", "", 1)
        # separate key and value
        _, _, val = str(overwrite).partition(":")
        owncloud_url = val
    return owncloud_url


values_file = None
if len(sys.argv) == 2:
    values_file = sys.argv[1]
else:
    value = input(
        "Sciebo RDS config file needed.\nvalues.yaml [./values.yaml]: ")
    if value != "":
        values_file = value
    else:
        values_file = "{}/values.yaml".format(os.getcwd())

values = None
try:
    with open(values_file, "r") as f:
        try:
            values = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(f"Error in values.yaml: {exc}")
            exit(1)
except OSError as exc:
    value = input(
        f"Missing file: {values_file}\nDo you want to create a new one? [Y/n]: ")
    if value == "" or value == "yes" or value == "y":
        values = {"global": {"domains": []}}
    else:
        exit(1)

if "global" not in values:
    values["global"] = {"domains": []}

if "domains" not in values["global"]:
    values["global"]["domains"] = []

config = None
with open("config.yaml", "r") as f:
    try:
        config = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"Error in config.yaml: {exc}")
        exit(1)

owncloud_path_global = config.get("owncloud_path", "")

for val in config["servers"]:
    key_filename = val.get("private_key")
    if key_filename is not None:
        key_filename = key_filename.replace("$HOME", os.environ["HOME"])

    client_id, client_secret = (random(), random())
    oauthname = config.get("oauthname", "sciebo-rds")
    rds_domain = config["rds"]

    owncloud_path = val.get("owncloud_path", owncloud_path_global)
    if owncloud_path != "" and not str(owncloud_path).endswith("/"):
        owncloud_path += "/"

    commands = [
        f'{owncloud_path}occ market:install oauth2',
        f'{owncloud_path}occ market:install rds',
        f'{owncloud_path}occ app:enable oauth2',
        f'{owncloud_path}occ app:enable rds',
        f'{owncloud_path}occ oauth2:add-client {oauthname} {client_id} {client_secret} {rds_domain}',
        f'{owncloud_path}occ rds:set-oauthname {oauthname}',
        f'{owncloud_path}occ rds:set-url {rds_domain}'
    ]
    owncloud_host_hostname_command = 'php -r "echo gethostname();"'
    owncloud_host_config_command = f'{owncloud_path}occ config:list | grep "overwritehost\|overwrite.cli.url"'

    owncloud_url = ""
    if "address" in val:
        ssh = paramiko.client.SSHClient()
        ssh.load_system_host_keys()
        ssh.connect(val["address"], username=val.get("user"),
                    password=val.get("password"), key_filename=key_filename)

        owncloud_url = execute(ssh, execute_ssh, commands,
                               owncloud_host_hostname_command, owncloud_host_config_command)

        ssh.close()
    elif "namespace" in val and "podname" in val:
        kubernetes.config.load_kube_config(
            context=val.get("k8scontext", config.get("k8scontext")))
        api = kubernetes.client.CoreV1Api()

        pods = api.list_namespaced_pod(
            namespace=val['namespace'], label_selector=val["selector"], field_selector="status.phase=Running")

        k8s = None
        for pod in pods:
            k8s = kubernetes.stream.stream(api.connect_get_namespaced_pod_exec(
                val["podname"], val['namespace'], command='/bin/bash', stderr=True, stdin=True, stdout=True, tty=True))

            if k8s.is_open():
                continue

        if k8s is None or not k8s.is_open():
            print(f"No connection via kubectl possible: {val}")
            exit(1)

        print(f"kubectl init: {k8s}")

        owncloud_url = execute(k8s, execute_kubectl, commands,
                               owncloud_host_hostname_command, owncloud_host_config_command)

        k8s.close()
    else:
        print(
            f"Skipped: Server was not valid to work with: {val}\nIt needs to be an object with `address` for ssh or `namespace` and `podname` for kubectl")
        continue

    if not owncloud_url:
        print(
            f"owncloud domain cannot be found automatically for {val}. Enter the correct domain without protocol. If port needed, add it too.\nExample: sciebords.uni-muenster.de, localhost:8000")
        value = ""

        while not value:
            value = input(f"Address: ")

        if value:
            owncloud_url = value
        else:
            exit(1)

    domain = {
        "name": val["name"],
        "ADDRESS": owncloud_url,
        "OAUTH_CLIENT_ID": client_id,
        "OAUTH_CLIENT_SECRET": client_secret
    }

    values["global"]["domains"].append(domain)

with open(values_file, 'w') as yaml_file:
    yaml.dump(values, yaml_file, default_flow_style=False)
