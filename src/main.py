#!/bin/env python3

import paramiko
from secrets import choice
import yaml
import string
import os
import sys


def random(N=64):
    ''.join([choice(string.ascii_lowercase +
                    string.ascii_uppercase + string.digits) for _ in range(N)])


def execute(ssh, cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    err = stderr.read()
    if err != "":
        print(f"Error in ssh command: {err}")
        exit(1)
    return stdout


values_file = None
if len(sys.argv) == 2:
    values_file = sys.argv[1]
else:
    value = input("Sciebo RDS config file needed.\nvalues.yaml [./values.yaml]: ")
    if value != "":
        values_file = value
    else:
        values_file = "{}/values.yaml".format(os.getcwd())

values = None
with open(values_file, "r") as f:
    try:
        values = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"Error in values.yaml: {exc}")
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

for val in config["sciebo"]:
    ssh = paramiko.client.SSHClient()
    ssh.load_system_host_keys()

    key_filename = val.get("private_key")
    if key_filename is not None:
        key_filename = key_filename.replace("$HOME", os.environ["HOME"])

    ssh.connect(val["address"], username=val.get("user"),
                password=val.get("password"), key_filename=key_filename)

    client_id, client_secret = (random(), random())
    oauthname = "sciebo-rds"
    rds_domain = config["rds"]

    owncloud_path = val.get("owncloud_path", owncloud_path_global)
    if owncloud_path != "" and not str(owncloud_path).endswith("/"):
        owncloud_path += "/"

    commands = [
        f'{owncloud_path}occ app:enable oauth2',
        f'{owncloud_path}occ app:enable rds',
        f'{owncloud_path}occ oauth2:add-client {oauthname} {client_id} {client_secret} {rds_domain}',
        f'{owncloud_path}occ rds:set-oauthname {oauthname}',
        f'{owncloud_path}occ rds:set-url {rds_domain}'
    ]

    for cmd in commands:
        execute(ssh, cmd)

    owncloud_url = ""

    # via php hostname
    owncloud_url = execute(ssh, 'php -r "echo gethostname();"').read()

    # via overwrites from config
    for overwrite in execute(ssh, f'{owncloud_path}occ config:list | grep "overwritehost\|overwrite.cli.url"').readlines():
        # remove comma, because we look at php dict parts
        overwrite = overwrite.replace(",", "")
        # separate key and value
        _, _, val = str(overwrite).partition(":")
        owncloud_url = val

    ssh.close()

    domain = {
        "name": val["name"],
        "ADDRESS": owncloud_url,
        "OAUTH_CLIENT_ID": client_id,
        "OAUTH_CLIENT_SECRET": client_secret
    }

    values["global"]["domains"].append(domain)

with open(values_file, 'w') as yaml_file:
    yaml.dump(values, yaml_file, default_flow_style=False)
