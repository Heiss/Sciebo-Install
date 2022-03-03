Status: not for production, yet

# Sciebo RDS CLI

This is a helper tool to install sciebo RDS to your owncloud instances. It supports ssh and kubectl.

## Usage

You need python3 and pip to use this tool.

```bash
git clone https://github.com/Heiss/Sciebo-RDS-Install.git && cd Sciebo-RDS-Install
pip install -r requirements.txt
chmod +x sciebo_rds_install/main.py
sciebo_rds_install/main.py --help
```

If you have poetry installed, you can use it. So the installation will not rubbish your local python environment, because it uses virtualenv on its own.

```bash
git clone https://github.com/Heiss/Sciebo-RDS-Install.git && cd Sciebo-RDS-Install
poetry install
poetry shell
sciebords --help
```

The application will look for a `values.yaml`, which is needed for the sciebo RDS helm supported installation process. So you only have to maintain a single yaml file. Just append the content of `config.yaml.example` to your `values.yaml`. But you can also set your config stuff for this tool in a separated `config.yaml` with `--config` flag. For options for the configuration, please take a look into the `config.yaml.example`, because it holds everything with documentation you can configure for this app. Also you should take a look into the help parameter, because it shows, what the tool can do for you.

## Developer installation

This project uses [poetry](https://python-poetry.org/docs/#installation) for dependencies. Install it with the described methods over there in the official poetry documentation.

Then you need to install the developer environment.

```bash
poetry install --with dev
poetry shell
```

After this you can run the application in this environment.

```bash
sciebords --help
```

If you add or update the dependencies, you have to generate a new requirementst.txt for easier user installations.

```bash
poetry export -f requirements.txt --output requirements.txt
```
