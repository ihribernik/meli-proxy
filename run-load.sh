#!/bin/bash

TARGET_URL=http://127.0.0.1:8000
TARGET_PATH=/health
artillery run deploy/load/artillery-50k.yml --output results.json
