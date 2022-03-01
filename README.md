# Sciebo RDS install

This is a helper tool to install sciebo RDS to your owncloud instances. It supports ssh and kubectl.

## Usage

You need python3 and pip to use this tool, but then it is easy to use.

```bash
git clone https://github.com/Heiss/Sciebo-Install.git && cd Sciebo-Install
pip install -r requirements.txt
chmod +x src/main.py
src/main.py --help
```

The application will look for a `config.yaml`. But you can also set your config stuff for this tool into the sciebo RDS needed `values.yaml`, so you only have to maintain a single yaml file. Just append the content of `config.yaml` to your `values.yaml`. For options, please take a look into the `config.yaml.example`, because it holds everything with documentation you can configure for this app. Also you should take a look into the help parameter, because it shows, what the tool can do for you.

## Developer installation

This project uses [poetry](https://python-poetry.org/docs/#installation) for dependencies. Install it with the described methods over there in the official poetry documentation.

Then you need to install the developer environment.

```bash
poetry install
```

After this you can run the application in this environment.

```bash
poetry run python src/main.py --help
```

If you add or update the dependencies, you have to generate a new requirementst.txt for easier user installations.

```bash
poetry export -f requirements.txt --output requirements.txt
```
