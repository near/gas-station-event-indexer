include .env

export $(shell sed 's/=.*//' .env)

# Configuration
VENV_NAME ?= .venv
PYTHON := $(VENV_NAME)/bin/python3
PIP := $(VENV_NAME)/bin/pip
REQUIREMENTS ?= requirements.txt

.PHONY: install clean

## install: create a virtual environment and install dependencies
install: $(VENV_NAME)
	@echo "Installing dependencies..."
	@$(PIP) install -r $(REQUIREMENTS)

$(VENV_NAME): 
	@test -d $(VENV_NAME) || python3 -m venv $(VENV_NAME)

## clean: remove virtual environment and temporary files
clean:
	@echo "Cleaning up..."
	rm -rf $(VENV_NAME)
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete

## run: gas station event indexer
run:
	@$(PYTHON) gas_station_event_indexer.py

## check: Format code, lint and type-check
check:
	black ./ && pylint *.py && mypy --strict *.py

help:
	@echo "Makefile for Python project with venv"
	@echo
	@echo "Usage:"
	@echo "  make install      create a virtual environment and install dependencies"
	@echo "  make clean        remove virtual environment and temporary files"
	@echo "  make help         show this help message"
