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


def get_commands():
    commands = [
        '{owncloud_path}occ market:install oauth2',
        '{owncloud_path}occ market:install rds',
        '{owncloud_path}occ app:enable oauth2',
        '{owncloud_path}occ app:enable rds',
        '{owncloud_path}occ oauth2:add-client {oauthname} {client_id} {client_secret} {rds_domain}',
        '{owncloud_path}occ rds:set-oauthname {oauthname}',
        '{owncloud_path}occ rds:set-url {rds_domain}'
    ]
    
    return commands

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
arguments = sys.argv
force_kubectl = False


if "--help" in arguments:
    print("""Usage: main.py values.yaml [--help|--only-kubeconfig|--commands]

--help: This dialog.
--only-kubeconfig: Ignore servers object in config.yaml and use the user kubeconfig for a single pod configuration.
--commands: Shows all commands, which will be executed to configure the owncloud instances properly.""")
    exit(1)

if "--only-kubeconfig" in arguments:
    force_kubectl = True
    arguments.remove("--only-kubeconfig")

if "--commands" in arguments:
    data = {
        "client_id": "{$CLIENT_ID}",
        "client_secret": "{$CLIENT_SECRET}",
        "oauthname": "{$OAUTHNAME}",
        "rds_domain": "{$RDS_DOMAIN}",
        "owncloud_path": "{$OWNCLOUD_PATH}"
    }

    print("""Conditions:
$CLIENT_ID and $CLIENT_SECRET has a length of 64.
$OWNCLOUD_PATH is empty "" (occ can be found through $PATH) or set to a folder with trailing slash / e.g. /var/www/owncloud/
$OAUTHNAME is not already in use for oauth2.
$RDS_DOMAIN points to the sciebo-rds installation root domain.

Remember that you also need the domainname of the owncloud instance to configure the values.yaml.
""")

    print("Commands: ")
    for cmd in get_commands():
        print(cmd.format(**data))
    exit(0)

if len(arguments) > 2:
    print("Error in parameters. Use --help for help.")
    exit(1)

if len(arguments) == 2:
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

if force_kubectl:
    try:
        config["servers"] = [{
            "selector": config["k8sselector"]
        }]
    except KeyError as exc:
        print("Missing `k8sselector` field in config. --only-kubeconfig needs this field.")
        exit(1)
    print("use kubeconfig only")


for val in config["servers"]:
    key_filename = val.get("private_key")
    if key_filename is not None:
        key_filename = key_filename.replace("{$HOME}", os.environ["HOME"])

    client_id, client_secret = (random(), random())
    oauthname = config.get("oauthname", "sciebo-rds")
    rds_domain = config["rds"]

    owncloud_path = val.get("owncloud_path", owncloud_path_global)
    if owncloud_path != "" and not str(owncloud_path).endswith("/"):
        owncloud_path += "/"

    data = {
        "client_id": client_id,
        "client_secret": client_secret, 
        "oauthname": oauthname, 
        "rds_domain": rds_domain, 
        "owncloud_pat": owncloud_path
    }
    commands = [cmd.format(**data) for cmd in get_commands()]

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
    elif "selector" in val:
        context = val.get("context", config.get("k8scontext"))
        selector = val.get("selector", config.get("k8sselector"))
        containername = val.get(
            "containername", config.get("k8scontainername"))
        kubernetes.config.load_kube_config(context=context)
        namespace = val.get("namespace", config.get(
            "k8snamespace", kubernetes.config.list_kube_config_contexts()[1]['context']['namespace']))
        api = kubernetes.client.CoreV1Api()

        pods = api.list_namespaced_pod(
            namespace=namespace, label_selector=selector, field_selector="status.phase=Running")

        k8s = None
        for pod in pods.items:
            k8s = kubernetes.stream.stream(
                api.connect_get_namespaced_pod_exec,
                pod.metadata.name,
                namespace,
                container=containername,
                command='/bin/bash',
                stderr=True, stdin=True, stdout=True, tty=False, _preload_content=False
            )

            if k8s.is_open():
                continue

        if k8s is None or not k8s.is_open():
            print(f"No connection via kubectl possible: {val}")
            exit(1)

        print(
            f"kubectl initialized: Connected to pod {pod.metadata.name}, container {containername} in namespace {namespace}")

        owncloud_url = execute(k8s, execute_kubectl, commands,
                               owncloud_host_hostname_command, owncloud_host_config_command)

        k8s.close()
    else:
        print(
            f"Skipped: Server was not valid to work with: {val}\nIt needs to be an object with `address` for ssh or `namespace` for kubectl")
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

exit(0)
