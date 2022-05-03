#!/bin/env python3

import click
import paramiko
import kubernetes
from secrets import choice
import yaml
import string
import os
import requests
from pathlib import Path


def random(N=64):
    return "".join(
        [
            choice(string.ascii_lowercase + string.ascii_uppercase + string.digits)
            for _ in range(N)
        ]
    )


def get_commands():
    commands = [
        # "{owncloud_path}occ market:install oauth2",
        # "{owncloud_path}occ market:install rds",
        "{owncloud_path}occ app:enable oauth2",
        "{owncloud_path}occ app:enable rds",
        "{owncloud_path}occ oauth2:add-client {oauthname} {client_id} {client_secret} {rds_domain}",
        "{owncloud_path}occ rds:set-oauthname {oauthname}",
        "{owncloud_path}occ rds:set-url {rds_domain}",
        "{owncloud_path}occ rds:create-keys",
    ]

    return commands


def execute_ssh(ssh, cmd):
    _, stdout, stderr = ssh.exec_command(cmd)
    err = stderr.read()
    if err != "":
        click.echo(f"Error in ssh command: {err}", err=True)
        exit(1)
    return stdout


def execute_kubectl(k8s, cmd):
    k8s.write_stdin(cmd + "\n")
    err = k8s.read_stderr()
    if err != "":
        click.echo(f"Error in kubectl command: {err}")
        exit(1)
    return k8s.read_stdout(timeout=3)


def execute_helm(values_file, install=False, dry_run=False):
    if install and not dry_run:
        click.echo("Preparing helm for sciebo RDS.")
        click.echo("Remove installed sciebo rds from k8s if it is already there.")
        os.system("helm uninstall sciebo-rds")
        click.echo("Remove sciebo RDS from helm repo list.")
        os.system("helm repo remove sciebo-rds")
        click.echo("Add sciebo RDS in helm repo list again.")
        os.system(
            "helm repo add sciebo-rds https://www.research-data-services.org/charts/stable"
        )
        click.echo("Update helm repo list.")
        os.system("helm repo up sciebo-rds")
        click.echo("Finish preparation.")

    click.echo("Installing sciebo RDS via helm.")
    cmd = f"helm upgrade -i sciebo-rds sciebo-rds/all --values {values_file}"

    if dry_run:
        cmd += " --dry-run"

    error_code = os.system(cmd)

    if error_code > 0:
        click.echo("There was an error while installing sciebo RDS via helm.")
    else:
        click.echo(
            "Sciebo RDS is installed now via helm. Check it out via `kubectl get pods`."
        )


def execute(
    channel, fun, commands, owncloud_host_hostname_command, owncloud_host_config_command
):
    for cmd in commands:
        click.echo(f"Running command: {cmd}")
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


@click.group()
def cli():
    pass


values_file_path = "values.yaml"
config_file_path = "config.yaml"
cert_file_path = "create_certs.sh"


@click.command()
@click.option(
    "--self-signed-cert",
    "-s",
    "self_signed",
    is_flag=True,
    default=False,
    help=f"Creates the script {cert_file_path} for self-signed certificates. Not recommended for production use, but handy for testing.",
)
@click.option(
    "--force",
    "-f",
    "overwrite_values",
    is_flag=True,
    default=False,
    help=f"Overwrites the {values_file_path}, if it already exists. Otherwise exits with statuscode greater then 0.",
)
@click.option(
    "--one-file",
    "-c",
    "single_file",
    is_flag=True,
    default=False,
    help=f"Writes down the needed config stuff in {values_file_path}. Otherwise it creates a separate file {config_file_path}.",
)
def init(self_signed, overwrite_values, single_file):
    """
    Initialize needed files for sciebo RDS. Places the files in the current folder.
    """
    if self_signed:
        click.echo("Self-signed script selected.")

        if not os.path.isfile(cert_file_path) or overwrite_values:
            if overwrite_values:
                click.echo(f"WARN: Overwrites {cert_file_path} if it exists.")

            cnt = requests.get(
                "https://raw.githubusercontent.com/Sciebo-RDS/Sciebo-RDS/release/getting-started/create_certs.sh.example"
            ).text
            with open(cert_file_path, "w") as f:
                f.write(cnt)
                click.echo(f"{cert_file_path} created.")
        else:
            click.echo(
                f"{cert_file_path} already in place. Delete it or use -f to overwrite it.",
                err=True,
            )

    cnt = requests.get(
        "https://raw.githubusercontent.com/Sciebo-RDS/Sciebo-RDS/release/getting-started/values.yaml.example"
    ).text

    cfg = requests.get(
        "https://raw.githubusercontent.com/Sciebo-RDS/Sciebo-RDS-CLI/develop/config.yaml.example"
    ).text

    if (not os.path.isfile(config_file_path) or overwrite_values) and not single_file:
        if overwrite_values:
            click.echo(f"WARN: Overwrites {config_file_path} if it exists.")

        with open(config_file_path, "w") as f:
            f.write(cfg)
            click.echo(f"{config_file_path} created.")

    if not os.path.isfile(values_file_path) or overwrite_values:
        if overwrite_values:
            click.echo(f"WARN: Overwrites {values_file_path} if it exists.")

        if single_file:
            click.echo(
                f"WARN: Places {config_file_path} content at the top of {values_file_path}."
            )
            cnt = cfg + "\n\n\n" + cnt

        with open(values_file_path, "w") as f:
            f.write(cnt)
            click.echo(f"{values_file_path} created.")
    else:
        click.echo(
            f"{values_file_path} already in place. Delete it or use -f to overwrite it.",
            err=True,
        )

    if not single_file:
        click.echo(
            f"Adjust the {values_file_path} and {config_file_path} to your needs with your favourite editor, before you `install` sciebo RDS."
        )
    else:
        click.echo(
            f"Adjust the {values_file_path} to your needs with your favourite editor, before you `install` sciebo RDS."
        )


@click.command()
@click.option(
    "--one-file",
    "-c",
    "single_file",
    is_flag=True,
    default=False,
    help=f"Writes down the needed config stuff in {values_file_path}. Otherwise it creates a separate file {config_file_path}.",
)
@click.option(
    "--helm-sciebords-name",
    "-n",
    "helm_name",
    default="sciebords",
    help="Use the given name for helm install process. Defaults to 'sciebords'.",
)
def checks(single_file, helm_name):
    """
    Runs several checks if all requirements for sciebo RDS are fulfilled.
    """

    error_found = False

    if not os.path.isfile(values_file_path):
        click.echo(f"values.yaml is not in place: {values_file_path}", err=True)
        error_found = True
        return

    if not single_file and not os.path.isfile(config_file_path):
        click.echo(f"config.yaml is not in place: {config_file_path}", err=True)
        error_found = True
        return

    if os.system("kubectl version") > 0:
        click.echo("kubectl not found", err=True)
        error_found = True

    if os.system("helm version") > 0:
        click.echo("helm not found", err=True)
        error_found = True

    if (
        os.path.isfile(values_file_path)
        and os.system(
            f"helm upgrade -i {helm_name} sciebo-rds/all --values {values_file_path} --dry-run"
        )
        > 0
    ):
        click.echo(f"{values_file_path} not valid. Helm founds error.", err=True)
        error_found = True

    if not error_found:
        click.echo("Everything is fine. You should be good to install sciebo RDS.")


@click.command()
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Execute install without any changes. WARNING: It connects to the ownCloud instances and your k8s cluster via SSH and Kubectl to get some informations. Nevertheless it does not change anything.",
)
@click.argument(
    "values_file",
    default=Path(f"{os.getcwd()}/values.yaml"),
    type=click.Path(exists=True),
)
def upgrade(dry_run, values_file):
    """
    A wrapper method for convenience to upgrade the sciebo RDS instance with helm. Use this command if you changed something in your values.yaml
    """
    execute_helm(values_file, install=False, dry_run=dry_run)


@click.command()
def commands():
    """
    Shows all commands, which will be executed to configure the owncloud instances properly.
    """

    data = {
        "client_id": "${CLIENT_ID}",
        "client_secret": "${CLIENT_SECRET}",
        "oauthname": "${OAUTHNAME}",
        "rds_domain": "${RDS_DOMAIN}",
        "owncloud_path": "${OWNCLOUD_PATH}",
    }

    click.echo(
        """Conditions:
$CLIENT_ID and $CLIENT_SECRET has a length of 64 characters (no special character like [/\.,] allowed).
$OWNCLOUD_PATH is empty "" (occ can be found through $PATH) or set to a folder with trailing slash / e.g. /var/www/owncloud/
$OAUTHNAME is not in use for oauth2 already.
$RDS_DOMAIN points to the sciebo-rds installation root domain.

Remember that you also need the domainname of the owncloud instance to configure the values.yaml, which will be automatically guessed by this script.

ownCloud needs php-gmp for oauth2 plugin. Install it on your own.
"""
    )

    click.echo("Commands: ")
    for cmd in get_commands():
        click.echo(cmd.format(**data))


@click.command()
@click.option(
    "--only-kubeconfig",
    "-k",
    "force_kubectl",
    is_flag=True,
    default=False,
    help="Ignore servers object in config.yaml and use the user kubeconfig for a single pod configuration.",
)
@click.option(
    "-h",
    "--helm-install",
    "helm_install",
    is_flag=True,
    default=False,
    help="A convenient parameter. It runs all needed helm commands to install sciebo-rds in your current kubectl context after configuration. Helm upgrades should not use this parameter. Please use `sciebords upgrade` for this.",
)
@click.option(
    "-c",
    "--config",
    "file",
    type=click.Path(exists=True),
    is_flag=False,
    flag_value=Path(f"{os.getcwd()}/config.yaml"),
    help="The given path will be used as config.yaml file. If not given, it will use the values.yaml per default as a single-file-configuration otherwise.",
)
@click.argument(
    "values_file",
    default=Path(f"{os.getcwd()}/values.yaml"),
    type=click.Path(exists=True),
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Execute install without any changes. WARNING: It connects to the ownCloud instances and your k8s cluster via SSH and Kubectl to get some informations. Nevertheless it does not change anything.",
)
def install(force_kubectl, helm_install, values_file, file, dry_run):
    """
    Use defined interfaces in given VALUES_FILE to get all needed informations from ownCloud installations and prepare the VALUES_FILE to install sciebo RDS.

    VALUES_FILE defaults to ./values.yaml. Take a look at --config to specify a different file for interface configuration.

    Primarily it sets up all needed plugins in ownCloud, gets everything in place and writes down the domains object in the values.yaml file, which will be used later to install sciebo RDS.
    """
    config_file = None
    values = None
    config = None

    try:
        with open(values_file, "r") as f:
            try:
                values = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                click.echo(f"Error in values.yaml: {exc}", err=True)
                exit(1)
    except OSError as exc:
        click.echo(f"Missing file: {values_file}", err=True)
        exit(1)

    if config_file is None:
        config = values
    else:
        try:
            with open(config_file, "r") as f:
                try:
                    config = yaml.safe_load(f)
                except yaml.YAMLError as exc:
                    click.echo(f"Error in config.yaml: {exc}", err=True)
                    exit(1)
        except OSError as exc:
            click.echo(f"Missing file: {config_file}", err=True)
            exit(1)

    owncloud_path_global = config.get("owncloud_path", "")

    if force_kubectl:
        try:
            config["servers"] = [{"selector": config["k8sselector"]}]
        except KeyError as exc:
            click.echo(
                "Missing `k8sselector` field in config. --only-kubeconfig needs this field.",
                err=True,
            )
            exit(1)
        click.echo("use kubeconfig only")

    servers = config.get("servers", [])

    if len(servers) == 0:
        click.echo("No servers were found.")
        exit(1)

    for val in servers:
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
            "owncloud_path": owncloud_path,
        }
        commands = [cmd.format(**data) for cmd in get_commands()]

        owncloud_host_hostname_command = 'php -r "echo gethostname();"'
        owncloud_host_config_command = (
            f'{owncloud_path}occ config:list | grep "overwritehost\|overwrite.cli.url"'
        )

        owncloud_url = ""
        if "address" in val:
            ssh = paramiko.client.SSHClient()
            ssh.load_system_host_keys()
            ssh.connect(
                val["address"],
                username=val.get("user"),
                password=val.get("password"),
                key_filename=key_filename,
            )

            if dry_run:
                click.echo(
                    "SSH can connect to ownCloud server: {}".format(val["address"])
                )
                continue

            owncloud_url = execute(
                ssh,
                execute_ssh,
                commands,
                owncloud_host_hostname_command,
                owncloud_host_config_command,
            )

            ssh.close()
        elif "namespace" in val:
            context = val.get("context", config.get("k8scontext"))
            selector = val.get("selector", config.get("k8sselector"))
            containername = val.get("containername", config.get("k8scontainername"))
            kubernetes.config.load_kube_config(context=context)
            namespace = val.get(
                "namespace",
                config.get(
                    "k8snamespace",
                    kubernetes.config.list_kube_config_contexts()[1]["context"][
                        "namespace"
                    ],
                ),
            )
            api = kubernetes.client.CoreV1Api()

            pods = api.list_namespaced_pod(
                namespace=namespace,
                label_selector=selector,
                field_selector="status.phase=Running",
            )

            k8s = None
            for pod in pods.items:
                k8s = kubernetes.stream.stream(
                    api.connect_get_namespaced_pod_exec,
                    pod.metadata.name,
                    namespace,
                    container=containername,
                    command="/bin/bash",
                    stderr=True,
                    stdin=True,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )

                if k8s.is_open():
                    continue

            if k8s is None or not k8s.is_open():
                click.echo(f"No connection via kubectl possible: {val}")
                exit(1)

            click.echo(
                f"kubectl initialized: Connected to pod {pod.metadata.name}, container {containername} in namespace {namespace}"
            )

            if dry_run:
                click.echo(
                    "kubectl can connect to ownCloud label: {}, container: {}".format(
                        selector, containername
                    )
                )
                continue

            owncloud_url = execute(
                k8s,
                execute_kubectl,
                commands,
                owncloud_host_hostname_command,
                owncloud_host_config_command,
            )

            k8s.close()
        else:
            click.echo(
                f"Skipped: Server was not valid to work with: {val}\nIt needs to be an object with `address` for ssh or `namespace` for kubectl"
            )
            continue

        if not owncloud_url:
            click.echo(
                f"owncloud domain cannot be found automatically for {val}. Enter the correct domain without protocol. If port needed, add it too.\nExample: sciebords.uni-muenster.de, localhost:8000"
            )
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
            "OAUTH_CLIENT_SECRET": client_secret,
        }

        values["global"]["domains"].append(domain)

    if not dry_run:
        with open(values_file, "w") as yaml_file:
            yaml.dump(values, yaml_file, default_flow_style=False)

    if helm_install:
        execute_helm(values_file, install=True, dry_run=dry_run)


cli.add_command(commands, "get-commands")
cli.add_command(init, "init")
cli.add_command(install, "install")
cli.add_command(checks, "checks")
cli.add_command(upgrade, "upgrade")


if __name__ == "__main__":
    cli()
