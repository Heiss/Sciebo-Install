# Sciebo RDS install

This is a helper tool to install sciebo RDS to your owncloud instances. It supports ssh and kubectl.

## Usage

You need python3 and pip to use this tool, but then it is easy to use.

```bash
pip install -r requirements.txt
chmod +x src/main.py
src/main.py --help
```

## Developer installation

This project uses [poetry](https://python-poetry.org/docs/#installation) for dependencies. Install it with the described methods over there in the official poetry documentation.

Then you need to install the developer environment.

```bash
poetry install
```

After this you can run the application in this environment.

```bash
poetry run python src/main.py
```

If you add or update the dependencies, you have to generate a new requirementst.txt for easier user installations.

```bash
poetry export -f requirements.txt --output requirements.txt
```
